import hmac
import json
import logging
import time
from secrets import token_urlsafe

from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from oauth2_provider.models import get_application_model


Application = get_application_model()
logger = logging.getLogger(__name__)

SUPPORTED_TOKEN_ENDPOINT_AUTH_METHODS = {
    "none": Application.CLIENT_PUBLIC,
    "client_secret_basic": Application.CLIENT_CONFIDENTIAL,
    "client_secret_post": Application.CLIENT_CONFIDENTIAL,
}
SUPPORTED_GRANT_TYPES = {"authorization_code", "refresh_token"}
SUPPORTED_RESPONSE_TYPES = {"code"}


def _base_url(request):
    return settings.PUBLIC_BASE_URL or request.build_absolute_uri("/").rstrip("/")


def _json_error(error, error_description, status=400):
    response = JsonResponse(
        {"error": error, "error_description": error_description},
        status=status,
    )
    response["Cache-Control"] = "no-store"
    response["Pragma"] = "no-cache"
    return response


def _set_no_store_headers(response):
    response["Cache-Control"] = "no-store"
    response["Pragma"] = "no-cache"
    return response


def _parse_json_request_body(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Request body must be valid JSON.") from exc

    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object.")

    return payload


def _get_string_list(payload, field_name, *, required=False, default=None):
    value = payload.get(field_name, default)
    if value is None:
        if required:
            raise ValueError(f"'{field_name}' is required.")
        return None

    if not isinstance(value, list) or not value:
        raise ValueError(f"'{field_name}' must be a non-empty array of strings.")

    normalized = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"'{field_name}' must contain only non-empty strings.")
        normalized.append(item.strip())
    return normalized


def _get_supported_scopes():
    return set(settings.OAUTH2_PROVIDER.get("SCOPES", {}).keys())


def _dcr_initial_access_token_ok(request):
    """Validate the optional RFC 7591 initial access token, if one is configured."""
    expected = settings.OAUTH2_DCR_INITIAL_ACCESS_TOKEN
    if not expected:
        return True

    header = request.META.get("HTTP_AUTHORIZATION", "")
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer" or not value:
        return False
    return hmac.compare_digest(value, expected)


@require_http_methods(["GET"])
def authorization_server_metadata(request):
    base_url = _base_url(request)
    metadata = {
        "issuer": base_url,
        "authorization_endpoint": f"{base_url}/oauth/authorize/",
        "token_endpoint": f"{base_url}/oauth/token/",
        "revocation_endpoint": f"{base_url}/oauth/revoke_token/",
        "introspection_endpoint": f"{base_url}/oauth/introspect/",
        "scopes_supported": sorted(settings.OAUTH2_PROVIDER["SCOPES"].keys()),
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": [
            "none",
            "client_secret_basic",
            "client_secret_post",
        ],
        "code_challenge_methods_supported": ["S256"],
    }
    # Only advertise registration when DCR is actually enabled.
    if settings.OAUTH2_DCR_ENABLED:
        metadata["registration_endpoint"] = f"{base_url}/oauth/register/"
    return JsonResponse(metadata)


@csrf_exempt
@require_http_methods(["POST"])
def dynamic_client_registration(request):
    if not settings.OAUTH2_DCR_ENABLED:
        return _json_error(
            "not_found",
            "Dynamic client registration is disabled.",
            status=404,
        )

    if not _dcr_initial_access_token_ok(request):
        return _json_error(
            "invalid_token",
            "A valid initial access token is required to register a client.",
            status=401,
        )

    try:
        payload = _parse_json_request_body(request)
        redirect_uris = _get_string_list(payload, "redirect_uris", required=True)
        grant_types = _get_string_list(
            payload,
            "grant_types",
            default=["authorization_code"],
        )
        response_types = _get_string_list(
            payload,
            "response_types",
            default=["code"],
        )
    except ValueError as exc:
        logger.warning("Invalid dynamic client registration payload: %s", exc)
        return _json_error("invalid_client_metadata", "Client metadata is invalid.")

    unsupported_grant_types = sorted(set(grant_types) - SUPPORTED_GRANT_TYPES)
    if unsupported_grant_types:
        return _json_error(
            "invalid_client_metadata",
            "Unsupported grant_types: " + ", ".join(unsupported_grant_types),
        )

    if "authorization_code" not in grant_types:
        return _json_error(
            "invalid_client_metadata",
            "grant_types must include 'authorization_code'.",
        )

    unsupported_response_types = sorted(set(response_types) - SUPPORTED_RESPONSE_TYPES)
    if unsupported_response_types:
        return _json_error(
            "invalid_client_metadata",
            "Unsupported response_types: "
            + ", ".join(unsupported_response_types),
        )

    if "code" not in response_types:
        return _json_error(
            "invalid_client_metadata",
            "response_types must include 'code'.",
        )

    token_endpoint_auth_method = payload.get(
        "token_endpoint_auth_method",
        "client_secret_basic",
    )
    if token_endpoint_auth_method not in SUPPORTED_TOKEN_ENDPOINT_AUTH_METHODS:
        return _json_error(
            "invalid_client_metadata",
            "Unsupported token_endpoint_auth_method: "
            + token_endpoint_auth_method,
        )

    supported_scopes = _get_supported_scopes()
    raw_scope = payload.get("scope", "mcp")
    if not isinstance(raw_scope, str):
        return _json_error(
            "invalid_client_metadata",
            "'scope' must be a space-delimited string.",
        )
    requested_scope = raw_scope.strip() or "mcp"
    requested_scopes = set(requested_scope.split())
    unsupported_scopes = sorted(requested_scopes - supported_scopes)
    if unsupported_scopes:
        return _json_error(
            "invalid_client_metadata",
            "Unsupported scope values: " + ", ".join(unsupported_scopes),
        )

    client_name = str(payload.get("client_name", "Dynamic MCP Client")).strip()
    if not client_name:
        client_name = "Dynamic MCP Client"

    client_secret = None
    client_type = SUPPORTED_TOKEN_ENDPOINT_AUTH_METHODS[token_endpoint_auth_method]
    if client_type == Application.CLIENT_CONFIDENTIAL:
        client_secret = token_urlsafe(48)

    application = Application(
        name=client_name,
        client_type=client_type,
        authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
        redirect_uris=" ".join(redirect_uris),
        skip_authorization=False,
        hash_client_secret=True,
        client_secret=client_secret or "",
    )

    try:
        application.full_clean()
    except ValidationError as exc:
        logger.warning("Dynamic client registration validation failed: %s", exc)
        return _json_error(
            "invalid_client_metadata",
            "Client metadata is invalid.",
        )

    application.save()

    response_payload = {
        "client_id": application.client_id,
        "client_id_issued_at": int(time.time()),
        "client_name": client_name,
        "redirect_uris": redirect_uris,
        # Report what was actually provisioned, not the raw request echo. The app
        # is created with the authorization_code grant; refresh_token is implicit
        # to that grant in django-oauth-toolkit rather than a separate capability.
        "grant_types": sorted(set(grant_types) & SUPPORTED_GRANT_TYPES),
        "response_types": sorted(set(response_types) & SUPPORTED_RESPONSE_TYPES),
        "scope": " ".join(sorted(requested_scopes)),
        "token_endpoint_auth_method": token_endpoint_auth_method,
    }
    if client_secret is not None:
        response_payload["client_secret"] = client_secret
        response_payload["client_secret_expires_at"] = 0

    return _set_no_store_headers(JsonResponse(response_payload, status=201))
