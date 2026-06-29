from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from oauth2_provider.models import get_access_token_model, get_application_model

from apps.users.models import APIToken

User = get_user_model()
Application = get_application_model()
AccessToken = get_access_token_model()


@override_settings(DEMO=True)
class DemoModeAPITests(TestCase):
    """The DEMO-mode gate (apps.api.permissions.NotInDemoMode) must reject
    API access regardless of the authentication method used, including the
    PAT and OAuth2 backends introduced for MCP integrations."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="demo@example.com",
            password="test-password",
        )

    def test_pat_cannot_access_api_in_demo_mode(self):
        _token, raw_token = APIToken.objects.create_token(
            user=self.user, name="n8n"
        )

        response = self.client.get(
            "/api/accounts/",
            HTTP_AUTHORIZATION=f"Token {raw_token}",
        )

        self.assertEqual(response.status_code, 403)

    def test_oauth_access_token_cannot_access_api_in_demo_mode(self):
        app = Application.objects.create(
            name="Test Client",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            redirect_uris="http://127.0.0.1:8765/callback",
            client_secret="secret",
        )
        access_token = AccessToken.objects.create(
            user=self.user,
            scope="mcp",
            expires=timezone.now() + timedelta(hours=1),
            token="demo-oauth-access-token-xyz",
            application=app,
        )

        response = self.client.get(
            "/api/accounts/",
            HTTP_AUTHORIZATION=f"Bearer {access_token.token}",
        )

        self.assertEqual(response.status_code, 403)

    def test_superuser_pat_can_access_api_in_demo_mode(self):
        admin = User.objects.create_superuser(
            email="admin@example.com",
            password="test-password",
        )
        _token, raw_token = APIToken.objects.create_token(
            user=admin, name="admin"
        )

        response = self.client.get(
            "/api/accounts/",
            HTTP_AUTHORIZATION=f"Token {raw_token}",
        )

        # NotInDemoMode grants superusers access in DEMO mode; the request is
        # authenticated by the PAT, so the API responds normally (never 403).
        self.assertNotEqual(response.status_code, 403)


@override_settings(DEMO=True)
class DemoModeOAuthEndpointTests(TestCase):
    """OAuth2 issuance and discovery endpoints must be disabled in DEMO mode
    so demo tenants cannot obtain (or even discover) credentials."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="demo@example.com",
            password="test-password",
        )

    def test_oauth_authorize_rejects_non_superuser_in_demo_mode(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("oauth2_provider:authorize"))

        self.assertEqual(response.status_code, 403)

    def test_oauth_token_rejects_non_superuser_in_demo_mode(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse("oauth2_provider:token"))

        self.assertEqual(response.status_code, 403)

    def test_oauth_authorization_server_metadata_rejects_in_demo_mode(self):
        response = self.client.get(reverse("oauth-authorization-server-metadata"))

        self.assertEqual(response.status_code, 403)

    def test_oauth_dynamic_client_registration_rejects_in_demo_mode(self):
        response = self.client.post(
            reverse("oauth-dynamic-client-registration"),
            data="{}",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)


@override_settings(DEMO=True)
class DemoModeAPITokenViewsTests(TestCase):
    """The PAT management UI must be disabled in DEMO mode just like the
    other mutating user views."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="demo@example.com",
            password="test-password",
        )
        self.client.force_login(self.user)
        self.htmx_headers = {"HTTP_HX_REQUEST": "true"}

    def test_cannot_create_api_token_from_ui_in_demo_mode(self):
        response = self.client.post(
            reverse("user_api_token_add"),
            {"name": "n8n", "expires_in_days": "30"},
            **self.htmx_headers,
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(APIToken.objects.count(), 0)

    def test_cannot_revoke_api_token_from_ui_in_demo_mode(self):
        token, _ = APIToken.objects.create_token(user=self.user, name="n8n")

        response = self.client.delete(
            reverse("user_api_token_revoke", kwargs={"token_id": token.id}),
            **self.htmx_headers,
        )

        self.assertEqual(response.status_code, 403)
        token.refresh_from_db()
        self.assertIsNone(token.revoked_at)

    def test_cannot_delete_api_token_from_ui_in_demo_mode(self):
        token, _ = APIToken.objects.create_token(user=self.user, name="n8n")

        response = self.client.delete(
            reverse("user_api_token_delete", kwargs={"token_id": token.id}),
            **self.htmx_headers,
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(APIToken.objects.filter(id=token.id).exists())