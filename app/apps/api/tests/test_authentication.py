from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed

from apps.api.authentication import APITokenAuthentication
from apps.users.models import APIToken


class APITokenAuthenticationTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.authentication = APITokenAuthentication()
        self.user = get_user_model().objects.create_user(
            email="automation@example.com",
            password="test-password",
        )

    def test_returns_none_without_token_header(self):
        request = self.factory.get("/api/accounts/")
        self.assertIsNone(self.authentication.authenticate(request))

    def test_authenticates_valid_api_token(self):
        token, raw_token = APIToken.objects.create_token(user=self.user, name="n8n")
        request = self.factory.get(
            "/api/accounts/",
            HTTP_AUTHORIZATION=f"Token {raw_token}",
        )

        authenticated_user, authenticated_token = self.authentication.authenticate(request)

        self.assertEqual(authenticated_user, self.user)
        self.assertEqual(authenticated_token.pk, token.pk)
        token.refresh_from_db()
        self.assertIsNotNone(token.last_used_at)

    def test_rejects_expired_api_token(self):
        token, raw_token = APIToken.objects.create_token(user=self.user, name="n8n")
        token.expires_at = timezone.now() - timedelta(minutes=1)
        token.save(update_fields=["expires_at"])
        request = self.factory.get(
            "/api/accounts/",
            HTTP_AUTHORIZATION=f"Token {raw_token}",
        )

        with self.assertRaisesRegex(AuthenticationFailed, "expired"):
            self.authentication.authenticate(request)

    def test_rejects_revoked_api_token(self):
        token, raw_token = APIToken.objects.create_token(user=self.user, name="n8n")
        token.revoked_at = timezone.now()
        token.save(update_fields=["revoked_at"])
        request = self.factory.get(
            "/api/accounts/",
            HTTP_AUTHORIZATION=f"Token {raw_token}",
        )

        with self.assertRaisesRegex(AuthenticationFailed, "revoked"):
            self.authentication.authenticate(request)

    def test_stores_secret_as_sha256_not_raw(self):
        token, raw_token = APIToken.objects.create_token(user=self.user, name="n8n")
        _key, secret = APIToken.parse_raw_token(raw_token)

        self.assertNotIn(secret, token.token_hash)
        self.assertEqual(len(token.token_hash), 64)
        self.assertTrue(token.check_secret(secret))

    def test_falls_through_for_non_prefixed_token(self):
        request = self.factory.get(
            "/api/accounts/",
            HTTP_AUTHORIZATION="Token deadbeefdeadbeefdeadbeef",
        )
        # Not our prefix: return None so another authenticator can handle it.
        self.assertIsNone(self.authentication.authenticate(request))

    @override_settings(API_TOKEN_LAST_USED_UPDATE_INTERVAL=600)
    def test_last_used_at_is_throttled_within_interval(self):
        token, raw_token = APIToken.objects.create_token(user=self.user, name="n8n")
        request = self.factory.get(
            "/api/accounts/",
            HTTP_AUTHORIZATION=f"Token {raw_token}",
        )

        self.authentication.authenticate(request)
        token.refresh_from_db()
        first_used = token.last_used_at
        self.assertIsNotNone(first_used)

        self.authentication.authenticate(request)
        token.refresh_from_db()
        self.assertEqual(token.last_used_at, first_used)

    @override_settings(API_TOKEN_LAST_USED_UPDATE_INTERVAL=0)
    def test_last_used_at_updates_after_interval(self):
        token, raw_token = APIToken.objects.create_token(user=self.user, name="n8n")
        token.last_used_at = timezone.now() - timedelta(minutes=5)
        token.save(update_fields=["last_used_at"])
        stale = token.last_used_at
        request = self.factory.get(
            "/api/accounts/",
            HTTP_AUTHORIZATION=f"Token {raw_token}",
        )

        self.authentication.authenticate(request)
        token.refresh_from_db()
        self.assertGreater(token.last_used_at, stale)
