"""Native MCP server (Streamable HTTP, stateless, JSON responses only).

Each tool runs the matching REST API view in-process, as the caller, so
permissions, sharing, filters, validation and signals stay the API's.
"""

import json
import logging
import re
from decimal import Decimal
from functools import cache
from threading import Lock
from urllib.parse import urlsplit

from django.conf import settings
from django.http import Http404
from django.test import RequestFactory
from django.urls import Resolver404, resolve
from drf_spectacular.generators import SchemaGenerator
from oauth2_provider.contrib.rest_framework import OAuth2Authentication
from rest_framework.exceptions import ParseError
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api import views
from apps.api.authentication import APITokenAuthentication
from apps.api.permissions import NotInDemoMode
from apps.common.oauth_views import _base_url

PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
INSTRUCTIONS = (
    "WYGIWYH is a personal finance tracker. Amounts are never negative: `type` "
    "IN is income and EX is expense. `reference_date` is the month a "
    "transaction counts toward: YYYY-MM in these tools, YYYY-MM-DD for recurring "
    "transactions and installment plans in call_api. Use summarize_transactions for totals instead "
    "of adding up search results. Look up ids with list_accounts and "
    "list_categories/list_tags/list_entities. For anything else, find the "
    "endpoint with search_api and run it with call_api."
)

_factory = RequestFactory()
logger = logging.getLogger(__name__)


class ToolError(Exception):
    pass


def _dispatch(request, view, method, *, path="/", kwargs=None, query=None, data=None):
    """Run an API view as the MCP caller and return its response data."""
    host = {"HTTP_HOST": request._request.get_host(), "secure": request.is_secure()}
    if method == "get":
        inner = _factory.get(path, query or {}, **host)
    else:
        inner = getattr(_factory, method)(
            path, json.dumps(data or {}), content_type="application/json", **host
        )
    inner._force_auth_user = request.user
    inner._force_auth_token = request.auth
    response = view(inner, **(kwargs or {}))
    if response.status_code >= 400:
        raise ToolError(response.data)
    return response.data


def _call_api(request, viewset, action, *, method="get", pk=None, query=None, data=None):
    return _dispatch(
        request,
        viewset.as_view({method: action}),
        method,
        kwargs={"pk": pk} if pk is not None else None,
        query=query,
        data=data,
    )


def _num(value):
    """'50.000000000000000000000000000000' -> '50'."""
    if value is None:
        return None
    return format(Decimal(str(value)).normalize(), "f")


def _clean(item):
    return {k: v for k, v in item.items() if v not in (None, "", [])}


def _names(items):
    return [i["name"] for i in items or []]


def _transaction(t):
    account = t["account"]
    exchanged = t["exchanged_amount"]  # {amount, prefix, suffix, ...} or None
    return _clean(
        {
            "id": t["id"],
            "date": t["date"],
            "reference_date": t["reference_date"],
            "type": t["type"],
            "is_paid": t["is_paid"],
            "amount": _num(t["amount"]),
            "currency": account["currency"]["code"],
            "exchanged": (
                f"{exchanged['prefix']}{_num(exchanged['amount'])}{exchanged['suffix']}"
                if exchanged
                else None
            ),
            "description": t["description"],
            "account": {"id": account["id"], "name": account["name"]},
            "category": t["category"]["name"] if t["category"] else None,
            "tags": _names(t["tags"]),
            "entities": _names(t["entities"]),
            "notes": t["notes"],
            "sub_transactions": [
                {"name": s["name"], "amount": _num(s["amount"])}
                for s in t["sub_transactions"]
            ],
            "mute": t["mute"] or None,
            "transfer_with": t["linked_transaction"],
            "installment_plan": t["installment_plan"],
            "recurring_transaction": t["recurring_transaction"],
        }
    )


def _page(data, compact):
    return {
        "count": data["count"],
        "has_more": data["next"] is not None,
        "results": [compact(item) for item in data["results"]],
    }


# --- tools -------------------------------------------------------------------

DATE = {"type": "string", "format": "date", "description": "YYYY-MM-DD"}
MONTH = {"type": "string", "description": "YYYY-MM"}
TYPE = {"type": "string", "enum": ["IN", "EX"], "description": "IN = income, EX = expense"}
ID = {"type": "integer"}
FILTERS = {
    "date_from": DATE,
    "date_to": DATE,
    "month_from": MONTH,
    "month_to": MONTH,
    "account_id": ID,
    "category_id": ID,
    "tag_id": ID,
    "entity_id": ID,
    "type": TYPE,
    "is_paid": {"type": "boolean"},
    "description": {"type": "string", "description": "Part of the description, case-insensitive"},
}
FILTER_PARAMS = {
    "date_from": "date__gte",
    "date_to": "date__lte",
    "month_from": "reference_date__gte",
    "month_to": "reference_date__lte",
    "account_id": "account",
    "category_id": "category",
    "tag_id": "tags",
    "entity_id": "entities",
    "type": "type",
    "is_paid": "is_paid",
    "description": "description__icontains",
}
TRANSACTION_FIELDS = {
    "account_id": ID,
    "type": TYPE,
    "amount": {"type": "string", "description": "Decimal, never negative"},
    "date": DATE,
    "reference_date": {**MONTH, "description": "YYYY-MM; when creating, defaults to the month of date"},
    "description": {"type": "string"},
    "is_paid": {"type": "boolean", "description": "false for a planned transaction; when creating, defaults to true"},
    "category": {
        "type": ["integer", "string", "null"],
        "description": "Category id or name; an unknown name creates the category; null clears it",
    },
    "tags": {
        "type": "array",
        "items": {"type": ["integer", "string"]},
        "description": "Tag ids or names; unknown names are created. Replaces the current tags.",
    },
    "entities": {
        "type": "array",
        "items": {"type": ["integer", "string"]},
        "description": "Entity ids or names; unknown names are created. Replaces the current entities.",
    },
    "notes": {"type": "string"},
    "mute": {"type": "boolean", "description": "Muted transactions are left out of totals"},
}


def _filters(args):
    query = {}
    for key, param in FILTER_PARAMS.items():
        if key in args:
            value = args[key]
            if isinstance(value, bool):
                value = str(value).lower()
            elif key.startswith("month_"):  # the filter takes full dates
                if not re.fullmatch(r"\d{4}-\d{2}", str(value)):
                    raise ToolError({key: "Use YYYY-MM."})
                value = f"{value}-01"
            query[param] = value
    return query


def _transaction_body(args):
    body = {k: v for k, v in args.items() if k in TRANSACTION_FIELDS}
    if "amount" in body:
        body["amount"] = str(body["amount"])
    return body


def list_accounts(request, args):
    query = {} if args.get("include_archived") else {"is_archived": "false"}
    data = _call_api(request, views.AccountViewSet, "list", query={**query, "page_size": 1000})
    return [
        _clean(
            {
                "id": a["id"],
                "name": a["name"],
                "group": a["group"]["name"] if a["group"] else None,
                "currency": a["currency"]["code"],
                "exchange_currency": (a["exchange_currency"] or {}).get("code"),
                "is_asset": a["is_asset"] or None,
                "is_investment": a["is_investment"] or None,
            }
        )
        for a in data["results"]
    ]


def get_account_balance(request, args):
    data = _call_api(request, views.AccountViewSet, "balance", pk=args["account_id"])
    return {
        "current_balance": _num(data["current_balance"]),
        "projected_balance": _num(data["projected_balance"]),
        "currency": data["currency"]["code"],
    }


def _filtered_transactions(request, action, query):
    """Like _call_api, but errors name the tool's filters, not the API's."""
    try:
        return _call_api(request, views.TransactionViewSet, action, query=query)
    except ToolError as e:
        detail = e.args[0]
        if isinstance(detail, dict):
            names = {param: arg for arg, param in FILTER_PARAMS.items()}
            detail = {names.get(k, k): v for k, v in detail.items()}
        raise ToolError(detail) from e


def search_transactions(request, args):
    query = _filters(args)
    query["page"] = args.get("page", 1)
    query["page_size"] = min(int(args.get("page_size", 50)), 100)
    query["ordering"] = "-date"
    return _page(_filtered_transactions(request, "list", query), _transaction)


def summarize_transactions(request, args):
    query = _filters(args)
    for key in ("group_by", "include_muted"):
        if key in args:
            query[key] = str(args[key]).lower()
    rows = _filtered_transactions(request, "summary", query)
    return [{**row, "total": _num(row["total"])} for row in rows]


def get_transaction(request, args):
    return _transaction(
        _call_api(request, views.TransactionViewSet, "retrieve", pk=args["id"])
    )


def create_transaction(request, args):
    return _transaction(
        _call_api(
            request,
            views.TransactionViewSet,
            "create",
            method="post",
            data=_transaction_body(args),
        )
    )


def update_transaction(request, args):
    return _transaction(
        _call_api(
            request,
            views.TransactionViewSet,
            "partial_update",
            method="patch",
            pk=args["id"],
            data=_transaction_body(args),
        )
    )


def delete_transaction(request, args):
    _call_api(request, views.TransactionViewSet, "destroy", method="delete", pk=args["id"])
    return {"deleted": args["id"]}


def _lister(viewset):
    def handler(request, args):
        query = {"page_size": 1000}
        if not args.get("include_inactive"):
            query["active"] = "true"
        if args.get("name"):
            query["name__icontains"] = args["name"]
        data = _call_api(request, viewset, "list", query=query)
        return [
            _clean(
                {
                    "id": i["id"],
                    "name": i["name"],
                    "inactive": not i["active"] or None,
                    "mute": i.get("mute") or None,  # categories only
                }
            )
            for i in data["results"]
        ]

    return handler


_operations_lock = Lock()


def _operations():
    # Schema generation isn't thread-safe; concurrent first calls broke it
    with _operations_lock:
        return _build_operations()


@cache
def _build_operations():
    """The REST API's operations from its OpenAPI schema, with $refs inlined."""
    schema = SchemaGenerator().get_schema(request=None, public=True)
    components = schema["components"]["schemas"]

    def inline(node, depth=0):
        if isinstance(node, list):
            return [inline(i, depth) for i in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            if depth > 4:  # recursive schemas
                return {"type": "object"}
            return inline(components[node["$ref"].rsplit("/", 1)[-1]], depth + 1)
        return {k: inline(v, depth) for k, v in node.items()}

    operations = []
    for path, item in schema["paths"].items():
        if not path.startswith("/api/"):
            continue
        for method, op in item.items():
            content = op.get("requestBody", {}).get("content", {})
            body = content.get("application/json") or next(iter(content.values()), None)
            operations.append(
                _clean(
                    {
                        "method": method.upper(),
                        "path": path,
                        "summary": op.get("summary"),
                        "description": op.get("description"),
                        # name -> enum, format or type; path params are in the path
                        "query": {
                            p["name"]: (lambda s: s.get("enum") or s.get("format") or s.get("type"))(
                                inline(p.get("schema") or {})
                            )
                            for p in op.get("parameters", [])
                            if p["in"] == "query"
                        },
                        "body": inline(body["schema"]) if body else None,
                    }
                )
            )
    return operations


def search_api(request, args):
    words = str(args.get("query", "")).lower().split()
    if not words:
        return [f"{op['method']} {op['path']}" + (f" — {op['summary']}" if "summary" in op else "") for op in _operations()]

    scored = []
    for op in _operations():
        exact = {op["method"].lower(), *op["path"].strip("/").split("/")}
        head = f"{op['method']} {op['path']} {op.get('summary', '')}".lower()
        text = f"{head} {op.get('description', '')}".lower()
        if all(w in text for w in words):
            score = sum(2 * (w in exact) + (w in head) for w in words)
            scored.append((-score, len(op["path"]), op))
    scored.sort(key=lambda s: s[:2])
    return [op for _, _, op in scored[: min(int(args.get("limit", 5)), 20)]]


def call_api(request, args):
    method = str(args["method"]).lower()
    if method not in ("get", "post", "put", "patch", "delete"):
        raise ToolError({"method": "Must be GET, POST, PUT, PATCH or DELETE."})
    url = urlsplit(str(args["path"]))
    if url.scheme or url.netloc:
        raise ToolError({"path": "Pass only the path, e.g. /api/accounts/."})
    path = url.path
    path = path if path.endswith("/") else f"{path}/"
    try:
        match = resolve(path)
    except Resolver404:
        match = None
    view_class = getattr(match.func, "cls", None) if match else None
    if not (view_class and view_class.__module__.startswith("apps.api.views")):
        raise ToolError({"path": "Not a WYGIWYH API endpoint; find one with search_api."})

    query = {
        k: str(v).lower() if isinstance(v, bool) else v
        for k, v in (args.get("query") or {}).items()
    }
    data = _dispatch(
        request, match.func, method, path=path, kwargs=match.kwargs, query=query, data=args.get("body")
    )
    return {"ok": True} if data is None else data


LISTER_INPUT = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Part of the name, case-insensitive"},
        "include_inactive": {"type": "boolean"},
    },
}
READ = {"readOnlyHint": True, "openWorldHint": False}
WRITE = {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False}

TOOLS = [
    {
        "name": "list_accounts",
        "description": "Accounts with their group and currency. Archived accounts are left out unless include_archived is true.",
        "inputSchema": {"type": "object", "properties": {"include_archived": {"type": "boolean"}}},
        "annotations": READ,
        "handler": list_accounts,
    },
    {
        "name": "get_account_balance",
        "description": "Current balance (paid transactions only) and projected balance (paid and unpaid) of an account.",
        "inputSchema": {"type": "object", "properties": {"account_id": ID}, "required": ["account_id"]},
        "annotations": READ,
        "handler": get_account_balance,
    },
    {
        "name": "search_transactions",
        "description": "Transactions matching the filters, newest date first. Paginated; page_size is at most 100.",
        "inputSchema": {
            "type": "object",
            "properties": {
                **FILTERS,
                "page": {"type": "integer", "minimum": 1},
                "page_size": {"type": "integer", "minimum": 1, "maximum": 100},
            },
        },
        "annotations": READ,
        "handler": search_transactions,
    },
    {
        "name": "summarize_transactions",
        "description": (
            "Totals and counts of the transactions matching the filters, per currency and type, "
            "optionally grouped by category, tag, entity, account or month. Muted transactions and "
            "those in muted categories (see list_categories) are left out unless include_muted is true. With tag or entity grouping, a transaction counts "
            "once per tag/entity. Transfers between accounts count as an expense and an income."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                **FILTERS,
                "group_by": {"type": "string", "enum": ["category", "tag", "entity", "account", "month"]},
                "include_muted": {"type": "boolean"},
            },
        },
        "annotations": READ,
        "handler": summarize_transactions,
    },
    {
        "name": "get_transaction",
        "description": "One transaction by id.",
        "inputSchema": {"type": "object", "properties": {"id": ID}, "required": ["id"]},
        "annotations": READ,
        "handler": get_transaction,
    },
    {
        "name": "create_transaction",
        "description": "Records an income or expense. Your transaction rules run on it, as when created in the app.",
        "inputSchema": {
            "type": "object",
            "properties": TRANSACTION_FIELDS,
            "required": ["account_id", "type", "amount", "date"],
        },
        "annotations": WRITE,
        "handler": create_transaction,
    },
    {
        "name": "update_transaction",
        "description": "Changes only the fields sent. Your transaction rules run on it, as when edited in the app.",
        "inputSchema": {
            "type": "object",
            "properties": {"id": ID, **TRANSACTION_FIELDS},
            "required": ["id"],
        },
        "annotations": {**WRITE, "idempotentHint": True},
        "handler": update_transaction,
    },
    {
        "name": "delete_transaction",
        "description": "Deletes a transaction. Deleting either side of a transfer deletes both.",
        "inputSchema": {"type": "object", "properties": {"id": ID}, "required": ["id"]},
        "annotations": {**WRITE, "destructiveHint": True, "idempotentHint": True},
        "handler": delete_transaction,
    },
    {
        "name": "list_categories",
        "description": "Transaction categories. Inactive ones are left out unless include_inactive is true.",
        "inputSchema": LISTER_INPUT,
        "annotations": READ,
        "handler": _lister(views.TransactionCategoryViewSet),
    },
    {
        "name": "list_tags",
        "description": "Transaction tags. Inactive ones are left out unless include_inactive is true.",
        "inputSchema": LISTER_INPUT,
        "annotations": READ,
        "handler": _lister(views.TransactionTagViewSet),
    },
    {
        "name": "list_entities",
        "description": "People and businesses on the other side of transactions. Inactive ones are left out unless include_inactive is true.",
        "inputSchema": LISTER_INPUT,
        "annotations": READ,
        "handler": _lister(views.TransactionEntityViewSet),
    },
    {
        "name": "search_api",
        "description": (
            "Finds REST API endpoints for anything the other tools don't cover: recurring "
            "transactions, installment plans, currencies, exchange rates, account groups, "
            "investment classes, DCA strategies, import runs. Returns each match's method, path, "
            "parameters and JSON body schema, to use with call_api. Without a query, lists every endpoint."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Words that must all appear, e.g. 'recurring list'"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20, "description": "Defaults to 5"},
            },
        },
        "annotations": READ,
        "handler": search_api,
    },
    {
        "name": "call_api",
        "description": (
            "Calls a REST API endpoint found with search_api, as you. Replace path parameters "
            "such as {id} with values. Responses are the API's full JSON; list endpoints are "
            "paginated (page, page_size). File uploads aren't supported."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "method": {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"]},
                "path": {"type": "string", "description": "e.g. /api/recurring-transactions/12/"},
                "query": {"type": "object", "description": "Query string parameters"},
                "body": {"type": "object", "description": "JSON body for POST, PUT and PATCH"},
            },
            "required": ["method", "path"],
        },
        "annotations": {**WRITE, "destructiveHint": True},
        "handler": call_api,
    },
]
TOOLS_BY_NAME = {tool["name"]: tool for tool in TOOLS}


# --- protocol ----------------------------------------------------------------


def _tool_result(data, is_error=False):
    return {
        "content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False, default=str)}],
        "isError": is_error,
    }


class RpcError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message


class MCPView(APIView):
    authentication_classes = [OAuth2Authentication, APITokenAuthentication]
    permission_classes = [IsAuthenticated, NotInDemoMode]
    parser_classes = [JSONParser]
    renderer_classes = [JSONRenderer]
    schema = None  # not part of the REST API docs

    def initial(self, request, *args, **kwargs):
        if not settings.MCP_ENABLED:
            raise Http404
        super().initial(request, *args, **kwargs)

    def get_authenticate_header(self, request):
        # Points MCP clients at the OAuth metadata (RFC 9728).
        url = f"{_base_url(request)}/.well-known/oauth-protected-resource/mcp"
        return f'Bearer resource_metadata="{url}"'

    def handle_exception(self, exc):
        # The body may be parsed during authentication, before post() runs
        if isinstance(exc, ParseError):
            return self._error(None, -32700, "Parse error")
        return super().handle_exception(exc)

    def post(self, request):
        message = request.data
        if (
            not isinstance(message, dict)
            or message.get("jsonrpc") != "2.0"
            or not isinstance(message.get("method"), str)
        ):
            return self._error(message.get("id") if isinstance(message, dict) else None, -32600, "Invalid Request")
        if "id" not in message:  # notification or response
            return Response(status=202)

        params = message.get("params") or {}
        try:
            result = self.handle(request, message["method"], params)
        except RpcError as e:
            return self._error(message["id"], e.code, e.message)
        return Response({"jsonrpc": "2.0", "id": message["id"], "result": result})

    def handle(self, request, method, params):
        if method == "initialize":
            requested = params.get("protocolVersion")
            return {
                "protocolVersion": requested if requested in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "WYGIWYH", "version": settings.APP_VERSION},
                "instructions": INSTRUCTIONS,
            }
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": [{k: v for k, v in t.items() if k != "handler"} for t in TOOLS]}
        if method == "tools/call":
            tool = TOOLS_BY_NAME.get(params.get("name"))
            if tool is None:
                raise RpcError(-32602, f"Unknown tool: {params.get('name')}")
            args = params.get("arguments") or {}
            if not isinstance(args, dict):
                raise RpcError(-32602, "arguments must be an object")
            missing = [k for k in tool["inputSchema"].get("required", []) if k not in args]
            if missing:
                return _tool_result({"missing": missing}, is_error=True)
            try:
                return _tool_result(tool["handler"](request, args))
            except ToolError as e:
                return _tool_result(e.args[0], is_error=True)
            except Exception:
                logger.exception("MCP tool %s failed", tool["name"])
                return _tool_result({"detail": "Internal server error."}, is_error=True)
        raise RpcError(-32601, f"Method not found: {method}")

    @staticmethod
    def _error(id_, code, message):
        return Response({"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}})
