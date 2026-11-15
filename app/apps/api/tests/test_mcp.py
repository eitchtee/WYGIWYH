import json
from datetime import date
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.accounts.models import Account
from apps.common.middleware.thread_local import write_current_user, delete_current_user
from apps.accounts.models import AccountGroup
from apps.currencies.models import Currency, ExchangeRate
from apps.transactions.models import Transaction, TransactionCategory, TransactionTag
from apps.users.models import APIToken

User = get_user_model()


@override_settings(MCP_ENABLED=True, PUBLIC_BASE_URL="https://money.example")
class MCPTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="me@example.com", password="x")
        self.other = User.objects.create_user(email="other@example.com", password="x")
        _token, self.raw_token = APIToken.objects.create_token(user=self.user, name="mcp")

        self.brl = Currency.objects.create(code="BRL", name="Real", decimal_places=2)
        self.account = self._as(self.user, Account.objects.create, name="Checking", currency=self.brl)
        self.food = self._as(self.user, TransactionCategory.objects.create, name="Food")
        self.muted = self._as(self.user, TransactionCategory.objects.create, name="Hidden", mute=True)
        for amount, category in ((10, self.food), (5.5, self.food), (100, self.muted)):
            self._as(
                self.user,
                Transaction.objects.create,
                account=self.account,
                type=Transaction.Type.EXPENSE,
                amount=Decimal(str(amount)),
                date=date(2026, 3, 5),
                reference_date=date(2026, 3, 1),
                category=category,
                is_paid=True,
            )

        other_account = self._as(self.other, Account.objects.create, name="Theirs", currency=self.brl)
        self.other_tx = self._as(
            self.other,
            Transaction.objects.create,
            account=other_account,
            type=Transaction.Type.EXPENSE,
            amount=Decimal("999"),
            date=date(2026, 3, 5),
            reference_date=date(2026, 3, 1),
        )

    @staticmethod
    def _as(user, create, **kwargs):
        write_current_user(user)  # owner comes from the current user
        try:
            return create(**kwargs)
        finally:
            delete_current_user()

    def _rpc(self, method, params=None, id_=1, auth=True):
        body = {"jsonrpc": "2.0", "method": method}
        if id_ is not None:
            body["id"] = id_
        if params is not None:
            body["params"] = params
        headers = {"HTTP_AUTHORIZATION": f"Token {self.raw_token}"} if auth else {}
        return self.client.post(
            "/mcp", json.dumps(body), content_type="application/json", **headers
        )

    def _tool(self, name, **arguments):
        response = self._rpc("tools/call", {"name": name, "arguments": arguments})
        self.assertEqual(response.status_code, 200, response.content)
        result = response.json()["result"]
        return result["isError"], json.loads(result["content"][0]["text"])

    @override_settings(MCP_ENABLED=False)
    def test_disabled_by_setting(self):
        self.assertEqual(self._rpc("ping").status_code, 404)
        self.assertEqual(self.client.get("/.well-known/oauth-protected-resource/mcp").status_code, 404)

    def test_unauthenticated_points_to_resource_metadata(self):
        response = self._rpc("ping", auth=False)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response["WWW-Authenticate"],
            'Bearer resource_metadata="https://money.example/.well-known/oauth-protected-resource/mcp"',
        )

        metadata = self.client.get("/.well-known/oauth-protected-resource/mcp").json()
        self.assertEqual(metadata["resource"], "https://money.example/mcp")
        self.assertEqual(metadata["authorization_servers"], ["https://money.example"])

    def test_handshake(self):
        result = self._rpc("initialize", {"protocolVersion": "2025-06-18"}).json()["result"]
        self.assertEqual(result["protocolVersion"], "2025-06-18")
        self.assertIn("tools", result["capabilities"])

        self.assertEqual(self._rpc("notifications/initialized", id_=None).status_code, 202)

        tools = self._rpc("tools/list").json()["result"]["tools"]
        self.assertIn("summarize_transactions", {t["name"] for t in tools})
        self.assertNotIn("handler", tools[0])

    def test_protocol_errors(self):
        self.assertEqual(self._rpc("nope").json()["error"]["code"], -32601)
        unknown_tool = self._rpc("tools/call", {"name": "nope"}).json()
        self.assertEqual(unknown_tool["error"]["code"], -32602)
        bad_json = self.client.post(
            "/mcp", "{", content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {self.raw_token}",
        )
        self.assertEqual(bad_json.json()["error"]["code"], -32700)

    def test_summary_leaves_out_muted_and_other_users(self):
        is_error, rows = self._tool("summarize_transactions", group_by="category", month_from="2026-03")
        self.assertFalse(is_error, rows)
        self.assertEqual(
            rows,
            [{"currency": "BRL", "type": "EX", "group": "Food", "group_id": self.food.id, "total": "15.5", "count": 2}],
        )

        _, with_muted = self._tool("summarize_transactions", include_muted=True)
        self.assertEqual(with_muted[0]["total"], "115.5")

    def test_search_is_compact_and_scoped(self):
        is_error, page = self._tool("search_transactions", category_id=self.food.id, page_size=1)
        self.assertFalse(is_error, page)
        self.assertEqual(page["count"], 2)
        self.assertTrue(page["has_more"])
        tx = page["results"][0]
        self.assertEqual(tx["account"], {"id": self.account.id, "name": "Checking"})
        self.assertEqual(tx["currency"], "BRL")
        self.assertEqual(tx["category"], "Food")
        self.assertIn(tx["amount"], ("10", "5.5"))

        is_error, error = self._tool("get_transaction", id=self.other_tx.id)
        self.assertTrue(is_error)

    def test_create_update_delete(self):
        is_error, created = self._tool(
            "create_transaction",
            account_id=self.account.id,
            type="IN",
            amount="1200.50",
            date="2026-04-02",
            description="Salary",
            tags=["Work"],
        )
        self.assertFalse(is_error, created)
        self.assertEqual(created["amount"], "1200.5")
        self.assertEqual(created["reference_date"], "2026-04")
        self.assertEqual(created["tags"], ["Work"])

        is_error, updated = self._tool("update_transaction", id=created["id"], is_paid=True)
        self.assertFalse(is_error, updated)
        self.assertTrue(updated["is_paid"])
        self.assertEqual(updated["description"], "Salary")

        is_error, _ = self._tool("delete_transaction", id=created["id"])
        self.assertFalse(is_error)
        self.assertFalse(Transaction.objects.filter(pk=created["id"]).exists())

    def test_search_api_finds_endpoints_with_their_inputs(self):
        _, everything = self._tool("search_api")
        self.assertIn("GET /api/currencies/", everything)
        self.assertFalse(any("/api/schema/" in line for line in everything))

        _, matches = self._tool("search_api", query="recurring post", limit=1)
        self.assertEqual(matches[0]["path"], "/api/recurring-transactions/")
        self.assertEqual(matches[0]["method"], "POST")
        self.assertIn("recurrence_type", matches[0]["body"]["properties"])

    def test_call_api_runs_endpoints_as_the_caller(self):
        is_error, own = self._tool("call_api", method="GET", path="/api/currencies", query={"code": "BRL"})
        self.assertFalse(is_error, own)
        self.assertEqual(own["results"][0]["code"], "BRL")

        is_error, _ = self._tool("call_api", method="GET", path=f"/api/transactions/{self.other_tx.id}/")
        self.assertTrue(is_error)

        is_error, deleted = self._tool(
            "call_api", method="DELETE", path=f"/api/categories/{self.muted.id}/"
        )
        self.assertFalse(is_error, deleted)
        self.assertFalse(TransactionCategory.objects.filter(pk=self.muted.id).exists())

    def test_call_api_only_reaches_the_api(self):
        for path in ("/api/schema/", "/api/", "/admin/", "/mcp"):
            is_error, error = self._tool("call_api", method="GET", path=path)
            self.assertTrue(is_error, path)
            self.assertIn("path", error)

    def test_exchanged_amount(self):
        usd = Currency.objects.create(code="USD", name="Dollar", decimal_places=2, prefix="US$ ")
        ExchangeRate.objects.create(from_currency=self.brl, to_currency=usd, rate=Decimal("0.2"), date=date(2026, 1, 1))
        self.account.exchange_currency = usd
        self.account.save()

        is_error, page = self._tool("search_transactions", category_id=self.food.id, date_from="2026-03-01")
        self.assertFalse(is_error, page)
        self.assertEqual({t["exchanged"] for t in page["results"]}, {"US$ 2", "US$ 1.1"})

    def test_category_can_be_cleared(self):
        tx = Transaction.objects.filter(category=self.food).first()
        is_error, updated = self._tool("update_transaction", id=tx.id, category=None)
        self.assertFalse(is_error, updated)
        self.assertNotIn("category", updated)

    def test_filter_errors_use_tool_argument_names(self):
        is_error, errors = self._tool("search_transactions", date_from="not-a-date")
        self.assertTrue(is_error)
        self.assertIn("date_from", errors)

        is_error, errors = self._tool("summarize_transactions", month_from="2026-03-01")
        self.assertTrue(is_error)
        self.assertEqual(errors, {"month_from": "Use YYYY-MM."})

    def test_exchange_rates_must_be_positive(self):
        usd = Currency.objects.create(code="USD", name="Dollar", decimal_places=2)
        is_error, errors = self._tool(
            "call_api", method="POST", path="/api/exchange-rates/",
            body={"from_currency_id": self.brl.id, "to_currency_id": usd.id, "rate": "-2", "date": "2026-01-01T00:00:00Z"},
        )
        self.assertTrue(is_error)
        self.assertIn("rate", errors)

    def test_unexpected_errors_are_tool_errors(self):
        with mock.patch.dict(
            "apps.api.mcp.TOOLS_BY_NAME",
            {"list_tags": {"name": "list_tags", "inputSchema": {}, "handler": mock.Mock(side_effect=ValueError)}},
        ):
            is_error, error = self._tool("list_tags")
        self.assertTrue(is_error)
        self.assertEqual(error, {"detail": "Internal server error."})

    def test_api_keeps_currency_spacing_and_group_owner(self):
        is_error, currency = self._tool(
            "call_api", method="POST", path="/api/currencies/",
            body={"code": "EUR", "name": "Euro", "prefix": "€ ", "suffix": " eur"},
        )
        self.assertFalse(is_error, currency)
        self.assertEqual((currency["prefix"], currency["suffix"]), ("€ ", " eur"))

        is_error, group = self._tool(
            "call_api", method="POST", path="/api/account-groups/",
            body={"name": "Planted", "owner": self.other.id},
        )
        self.assertFalse(is_error, group)
        self.assertEqual(AccountGroup.all_objects.get(pk=group["id"]).owner, self.user)

    def test_api_rejects_bad_amounts_and_intervals(self):
        common = {"account": self.account.id, "type": "EX", "description": "x", "start_date": "2026-04-01"}
        cases = [
            ("/api/installment-plans/", {**common, "installment_amount": "-10", "number_of_installments": 2, "recurrence": "monthly"}, "installment_amount"),
            ("/api/recurring-transactions/", {**common, "amount": "10", "recurrence_type": "month", "recurrence_interval": 0}, "recurrence_interval"),
        ]
        for path, body, field in cases:
            is_error, errors = self._tool("call_api", method="POST", path=path, body=body)
            self.assertTrue(is_error, path)
            self.assertIn(field, errors)

    def test_accounts_can_be_archived_and_performance_needs_an_investment(self):
        is_error, _ = self._tool(
            "call_api", method="PATCH", path=f"/api/accounts/{self.account.id}/", body={"is_archived": True}
        )
        self.assertFalse(is_error)
        self.account.refresh_from_db()
        self.assertTrue(self.account.is_archived)

        is_error, _ = self._tool("call_api", method="GET", path=f"/api/accounts/{self.account.id}/performance/")
        self.assertTrue(is_error)

    def test_tag_filter_muted_categories_and_month_order(self):
        _, created = self._tool(
            "create_transaction", account_id=self.account.id, type="EX", amount="7", date="2026-01-02", tags=["Trip"]
        )
        tag = TransactionTag.all_objects.get(name="Trip")
        _, page = self._tool("search_transactions", tag_id=tag.id)
        self.assertEqual([t["id"] for t in page["results"]], [created["id"]])

        _, categories = self._tool("list_categories")
        self.assertEqual({c["name"]: c.get("mute") for c in categories}, {"Food": None, "Hidden": True})

        _, months = self._tool("summarize_transactions", group_by="month")
        self.assertEqual([m["group"] for m in months], ["2026-01", "2026-03"])

    def test_search_api_ranking_and_call_api_rejects_urls(self):
        _, matches = self._tool("search_api", query="transactions post", limit=1)
        self.assertEqual(matches[0]["path"], "/api/transactions/")

        is_error, error = self._tool("call_api", method="GET", path="http://elsewhere.invalid/api/accounts/")
        self.assertTrue(is_error)
        self.assertIn("path", error)

    def test_tool_validation_errors_are_tool_results(self):
        is_error, missing = self._tool("create_transaction", account_id=self.account.id)
        self.assertTrue(is_error)
        self.assertEqual(set(missing["missing"]), {"type", "amount", "date"})

        is_error, errors = self._tool(
            "create_transaction", account_id=self.account.id, type="EX", amount="-1", date="2026-04-02"
        )
        self.assertTrue(is_error)
        self.assertIn("amount", errors)
