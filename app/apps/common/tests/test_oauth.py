import os
import json
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from django.urls import reverse
from oauth2_provider.models import get_application_model

from apps.users.models import APIToken

Application = get_application_model()


@override_settings(
    PUBLIC_BASE_URL="https://wygiwyh.example.com",
    SECRET_KEY="test-secret-key",
    OAUTH2_PROVIDER={"SCOPES": {"mcp": "Access WYGIWYH from MCP clients."}},
)
class AuthorizationServerMetadataTests(SimpleTestCase):
    @override_settings(OAUTH2_DCR_ENABLED=True)
    def test_returns_oauth_authorization_server_metadata(self):
        response = self.client.get(reverse("oauth-authorization-server-metadata"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["issuer"], "https://wygiwyh.example.com")
        self.assertEqual(
            response.json()["authorization_endpoint"],
            "https://wygiwyh.example.com/oauth/authorize/",
        )
        self.assertEqual(
            response.json()["registration_endpoint"],
            "https://wygiwyh.example.com/oauth/register/",
        )
        self.assertEqual(response.json()["scopes_supported"], ["mcp"])
        self.assertIn("none", response.json()["token_endpoint_auth_methods_supported"])

    @override_settings(OAUTH2_DCR_ENABLED=False)
    def test_omits_registration_endpoint_when_dcr_disabled(self):
        response = self.client.get(reverse("oauth-authorization-server-metadata"))

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("registration_endpoint", response.json())


@override_settings(
    PUBLIC_BASE_URL="https://wygiwyh.example.com",
    SECRET_KEY="test-secret-key",
    OAUTH2_PROVIDER={"SCOPES": {"mcp": "Access WYGIWYH from MCP clients."}},
    OAUTH2_DCR_ENABLED=True,
    OAUTH2_DCR_INITIAL_ACCESS_TOKEN="",
)
class DynamicClientRegistrationTests(TestCase):
    def test_registers_public_client_for_pkce_flow(self):
        response = self.client.post(
            reverse("oauth-dynamic-client-registration"),
            data=json.dumps(
                {
                    "client_name": "Copilot MCP",
                    "redirect_uris": ["http://127.0.0.1:8765/callback"],
                    "grant_types": ["authorization_code", "refresh_token"],
                    "response_types": ["code"],
                    "scope": "mcp",
                    "token_endpoint_auth_method": "none",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["client_name"], "Copilot MCP")
        self.assertEqual(
            payload["redirect_uris"],
            ["http://127.0.0.1:8765/callback"],
        )
        self.assertEqual(
            payload["grant_types"],
            ["authorization_code", "refresh_token"],
        )
        self.assertEqual(payload["response_types"], ["code"])
        self.assertEqual(payload["scope"], "mcp")
        self.assertEqual(payload["token_endpoint_auth_method"], "none")
        self.assertNotIn("client_secret", payload)

        application = Application.objects.get(client_id=payload["client_id"])
        self.assertEqual(application.name, "Copilot MCP")
        self.assertEqual(application.client_type, Application.CLIENT_PUBLIC)
        self.assertEqual(
            application.authorization_grant_type,
            Application.GRANT_AUTHORIZATION_CODE,
        )
        self.assertEqual(
            application.redirect_uris,
            "http://127.0.0.1:8765/callback",
        )

    def test_registers_confidential_client_with_generated_secret(self):
        response = self.client.post(
            reverse("oauth-dynamic-client-registration"),
            data=json.dumps(
                {
                    "client_name": "Confidential MCP",
                    "redirect_uris": ["http://127.0.0.1:8765/callback"],
                    "token_endpoint_auth_method": "client_secret_basic",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["token_endpoint_auth_method"], "client_secret_basic")
        self.assertEqual(payload["scope"], "mcp")
        self.assertEqual(payload["client_secret_expires_at"], 0)
        self.assertTrue(payload["client_secret"])

        application = Application.objects.get(client_id=payload["client_id"])
        self.assertEqual(application.client_type, Application.CLIENT_CONFIDENTIAL)
        self.assertTrue(check_password(payload["client_secret"], application.client_secret))

    def test_rejects_unsupported_token_auth_method(self):
        response = self.client.post(
            reverse("oauth-dynamic-client-registration"),
            data=json.dumps(
                {
                    "redirect_uris": ["http://127.0.0.1:8765/callback"],
                    "token_endpoint_auth_method": "private_key_jwt",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_client_metadata")
        self.assertIn("token_endpoint_auth_method", response.json()["error_description"])

    def test_rejects_missing_redirect_uris(self):
        response = self.client.post(
            reverse("oauth-dynamic-client-registration"),
            data=json.dumps({"client_name": "No redirect"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_client_metadata")
        self.assertIn("redirect_uris", response.json()["error_description"])

    @override_settings(OAUTH2_DCR_ENABLED=False)
    def test_returns_404_when_dcr_disabled(self):
        response = self.client.post(
            reverse("oauth-dynamic-client-registration"),
            data=json.dumps({"redirect_uris": ["http://127.0.0.1:8765/callback"]}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(Application.objects.count(), 0)


@override_settings(
    PUBLIC_BASE_URL="https://wygiwyh.example.com",
    SECRET_KEY="test-secret-key",
    OAUTH2_PROVIDER={"SCOPES": {"mcp": "Access WYGIWYH from MCP clients."}},
    OAUTH2_DCR_ENABLED=True,
    OAUTH2_DCR_INITIAL_ACCESS_TOKEN="s3cret-iat",
)
class DynamicClientRegistrationInitialAccessTokenTests(TestCase):
    def test_rejects_registration_without_initial_access_token(self):
        response = self.client.post(
            reverse("oauth-dynamic-client-registration"),
            data=json.dumps({"redirect_uris": ["http://127.0.0.1:8765/callback"]}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "invalid_token")
        self.assertEqual(Application.objects.count(), 0)

    def test_allows_registration_with_initial_access_token(self):
        response = self.client.post(
            reverse("oauth-dynamic-client-registration"),
            data=json.dumps(
                {
                    "redirect_uris": ["http://127.0.0.1:8765/callback"],
                    "token_endpoint_auth_method": "none",
                }
            ),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer s3cret-iat",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Application.objects.count(), 1)


class SetupOAuthCommandTests(TestCase):
    @patch.dict(
        os.environ,
        {
            "MCP_OAUTH_CLIENT_ID": "mcp-wygiwyh",
            "MCP_OAUTH_CLIENT_SECRET": "super-secret",
            "MCP_OAUTH_REDIRECT_URIS": "http://127.0.0.1:8765/callback",
        },
        clear=False,
    )
    def test_creates_mcp_oauth_application(self):
        call_command("setup_oauth")

        application = Application.objects.get(client_id="mcp-wygiwyh")
        self.assertEqual(application.name, "WYGIWYH MCP")
        self.assertEqual(application.client_type, Application.CLIENT_CONFIDENTIAL)
        self.assertEqual(
            application.authorization_grant_type,
            Application.GRANT_AUTHORIZATION_CODE,
        )
        self.assertEqual(
            application.redirect_uris,
            "http://127.0.0.1:8765/callback",
        )
        self.assertFalse(application.skip_authorization)
        self.assertTrue(check_password("super-secret", application.client_secret))

    @patch.dict(
        os.environ,
        {
            "MCP_OAUTH_CLIENT_ID": "mcp-wygiwyh",
            "MCP_OAUTH_CLIENT_SECRET": "new-secret",
            "MCP_OAUTH_REDIRECT_URIS": "http://127.0.0.1:8765/callback http://localhost:8765/callback",
            "MCP_OAUTH_CLIENT_NAME": "WYGIWYH MCP Production",
            "MCP_OAUTH_SKIP_AUTHORIZATION": "true",
        },
        clear=False,
    )
    def test_updates_existing_mcp_oauth_application(self):
        Application.objects.create(
            client_id="mcp-wygiwyh",
            client_secret="old-secret",
            name="Old Name",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            redirect_uris="http://127.0.0.1:8765/callback",
            skip_authorization=False,
        )

        call_command("setup_oauth")

        application = Application.objects.get(client_id="mcp-wygiwyh")
        self.assertEqual(application.name, "WYGIWYH MCP Production")
        self.assertEqual(
            application.redirect_uris,
            "http://127.0.0.1:8765/callback http://localhost:8765/callback",
        )
        self.assertTrue(application.skip_authorization)
        self.assertTrue(check_password("new-secret", application.client_secret))


class CreateAPITokenCommandTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="n8n@example.com",
            password="test-password",
        )

    def test_creates_hashed_api_token_and_prints_raw_value(self):
        stdout = StringIO()

        call_command(
            "create_api_token",
            self.user.email,
            "--name",
            "n8n sync",
            stdout=stdout,
        )

        token = APIToken.objects.get(user=self.user, name="n8n sync")
        lines = [line.strip() for line in stdout.getvalue().splitlines() if line.strip()]
        raw_token = lines[-1]

        self.assertTrue(raw_token.startswith(APIToken.TOKEN_PREFIX))
        self.assertNotEqual(token.token_hash, raw_token)
        self.assertTrue(token.check_secret(APIToken.parse_raw_token(raw_token)[1]))

    def test_supports_expiring_tokens(self):
        call_command(
            "create_api_token",
            self.user.email,
            "--expires-in-days",
            "7",
        )

        token = APIToken.objects.get(user=self.user)
        self.assertIsNotNone(token.expires_at)
        self.assertGreater(token.expires_at, timezone.now())
