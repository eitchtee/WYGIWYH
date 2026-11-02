import base64

from django.contrib.auth import (
    BACKEND_SESSION_KEY,
    SESSION_KEY,
    authenticate,
    get_user_model,
)
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.users.models import APIToken


class UserAPITokenViewsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="user@example.com",
            password="test-password",
        )
        self.client.force_login(self.user)
        self.htmx_headers = {"HTTP_HX_REQUEST": "true"}

    def test_user_settings_renders_api_token_section(self):
        response = self.client.get(reverse("user_settings"), **self.htmx_headers)

        self.assertContains(response, "API Tokens")
        self.assertContains(response, reverse("user_api_token_add"))

    def test_can_create_api_token_from_ui(self):
        response = self.client.post(
            reverse("user_api_token_add"),
            {"name": "n8n", "expires_in_days": "30"},
            **self.htmx_headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Copy this token now")
        self.assertEqual(APIToken.objects.filter(user=self.user, name="n8n").count(), 1)

    def test_can_revoke_own_api_token(self):
        token, _ = APIToken.objects.create_token(user=self.user, name="n8n")

        response = self.client.delete(
            reverse("user_api_token_revoke", kwargs={"token_id": token.id}),
            **self.htmx_headers,
        )

        self.assertEqual(response.status_code, 200)
        token.refresh_from_db()
        self.assertIsNotNone(token.revoked_at)
        self.assertContains(response, "Revoked")

    def test_can_delete_revoked_api_token(self):
        token, _ = APIToken.objects.create_token(user=self.user, name="n8n")
        token.revoked_at = timezone.now()
        token.save(update_fields=["revoked_at"])

        response = self.client.delete(
            reverse("user_api_token_delete", kwargs={"token_id": token.id}),
            **self.htmx_headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(APIToken.objects.filter(id=token.id).exists())

    def test_cannot_delete_other_users_api_token(self):
        other = get_user_model().objects.create_user(
            email="other@example.com", password="test-password"
        )
        token, _ = APIToken.objects.create_token(user=other, name="theirs")

        response = self.client.delete(
            reverse("user_api_token_delete", kwargs={"token_id": token.id}),
            **self.htmx_headers,
        )

        self.assertEqual(response.status_code, 404)
        self.assertTrue(APIToken.objects.filter(id=token.id).exists())


def _oidc_providers(trust_email=False):
    return {
        "openid_connect": {
            "APPS": [
                {
                    "provider_id": "test-oidc",
                    "name": "Test OIDC",
                    "client_id": "client",
                    "secret": "secret",
                    "settings": {
                        "server_url": "https://idp.example.com",
                        "verified_email": trust_email,
                    },
                }
            ]
        }
    }


def _complete_oidc_login(claims):
    from allauth.core import context
    from allauth.socialaccount.adapter import get_adapter
    from allauth.socialaccount.helpers import complete_social_login
    from django.contrib.messages.middleware import MessageMiddleware
    from django.contrib.sessions.middleware import SessionMiddleware
    from django.contrib.auth.models import AnonymousUser
    from django.test import RequestFactory

    request = RequestFactory().get("/auth/oidc/test-oidc/login/callback/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = AnonymousUser()

    provider = get_adapter().get_provider(request, "test-oidc")
    sociallogin = provider.sociallogin_from_response(request, claims)
    sociallogin.state = {"process": "login"}
    with context.request_context(request):
        complete_social_login(request, sociallogin)
    return request


class OIDCEmailAutoConnectTests(TestCase):
    """GHSA-prgm-wrjv-fvrh: OIDC logins must only link to existing local
    accounts by email when the email is verified (or explicitly trusted)."""

    def setUp(self):
        self.victim = get_user_model().objects.create_superuser(
            email="Victim@example.com", password="victim-password"
        )

    def _login(self, claims):
        return _complete_oidc_login(claims)

    def _assert_not_linked(self, request):
        from allauth.socialaccount.models import SocialAccount

        self.assertFalse(SocialAccount.objects.filter(user=self.victim).exists())
        self.assertNotEqual(
            request.session.get("_auth_user_id"), str(self.victim.pk)
        )

    def _assert_linked(self, request):
        from allauth.socialaccount.models import SocialAccount

        self.assertTrue(
            SocialAccount.objects.filter(user=self.victim, uid="oidc-uid").exists()
        )
        self.assertEqual(request.session.get("_auth_user_id"), str(self.victim.pk))

    @override_settings(SOCIALACCOUNT_PROVIDERS=_oidc_providers())
    def test_unverified_email_is_not_linked(self):
        request = self._login(
            {"sub": "oidc-uid", "email": "victim@example.com", "email_verified": False}
        )
        self._assert_not_linked(request)

    @override_settings(SOCIALACCOUNT_PROVIDERS=_oidc_providers())
    def test_missing_email_verified_claim_is_not_linked(self):
        request = self._login({"sub": "oidc-uid", "email": "VICTIM@example.com"})
        self._assert_not_linked(request)

    @override_settings(SOCIALACCOUNT_PROVIDERS=_oidc_providers())
    def test_verified_email_is_linked(self):
        request = self._login(
            {"sub": "oidc-uid", "email": "victim@example.com", "email_verified": True}
        )
        self._assert_linked(request)

    @override_settings(SOCIALACCOUNT_PROVIDERS=_oidc_providers(trust_email=True))
    def test_trusted_provider_links_without_email_verified_claim(self):
        request = self._login({"sub": "oidc-uid", "email": "victim@example.com"})
        self._assert_linked(request)

    @override_settings(SOCIALACCOUNT_PROVIDERS=_oidc_providers(trust_email=True))
    def test_trusted_provider_links_explicitly_unverified_email(self):
        request = self._login(
            {"sub": "oidc-uid", "email": "victim@example.com", "email_verified": False}
        )
        self._assert_linked(request)


SOCIAL_ONLY_BACKEND = "apps.users.backends.SocialOnlyAuthenticationBackend"

# The login page loads static files, which the default manifest storage can
# only find after collectstatic.
PLAIN_STATIC_FILES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


def _basic_auth(email, password):
    credentials = base64.b64encode(f"{email}:{password}".encode()).decode()
    return f"Basic {credentials}"


@override_settings(STORAGES=PLAIN_STATIC_FILES, WHITENOISE_AUTOREFRESH=True)
class LocalLoginEnabledByDefaultTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="user@example.com", password="test-password"
        )

    def test_password_authenticates(self):
        self.assertEqual(
            authenticate(username="user@example.com", password="test-password"),
            self.user,
        )

    def test_login_page_shows_the_password_form(self):
        response = self.client.get(reverse("login"))

        self.assertContains(response, 'name="password"')

    def test_api_basic_auth_works(self):
        response = self.client.get(
            "/api/accounts/",
            HTTP_AUTHORIZATION=_basic_auth("user@example.com", "test-password"),
        )

        self.assertEqual(response.status_code, 200)


@override_settings(
    AUTHENTICATION_BACKENDS=[SOCIAL_ONLY_BACKEND],
    OIDC_DISABLE_LOCAL_LOGIN=True,
    SOCIALACCOUNT_PROVIDERS=_oidc_providers(trust_email=True),
    STORAGES=PLAIN_STATIC_FILES,
    WHITENOISE_AUTOREFRESH=True,
)
class LocalLoginDisabledTests(TestCase):
    """OIDC_DISABLE_LOCAL_LOGIN: passwords are refused everywhere, while OIDC
    logins and permission checks keep working."""

    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            email="user@example.com", password="test-password"
        )

    def test_password_does_not_authenticate(self):
        self.assertIsNone(
            authenticate(username="user@example.com", password="test-password")
        )
        self.assertIsNone(
            authenticate(email="user@example.com", password="test-password")
        )

    def test_login_page_hides_the_password_form(self):
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="password"')
        self.assertContains(response, "Test OIDC")

    def test_login_page_refuses_a_password(self):
        self.client.post(
            reverse("login"),
            {"username": "user@example.com", "password": "test-password"},
        )

        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_admin_refuses_a_password(self):
        self.client.post(
            reverse("admin:login"),
            {"username": "user@example.com", "password": "test-password"},
        )

        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_api_basic_auth_is_refused(self):
        response = self.client.get(
            "/api/accounts/",
            HTTP_AUTHORIZATION=_basic_auth("user@example.com", "test-password"),
        )

        self.assertIn(response.status_code, (401, 403))

    def test_oidc_login_still_works(self):
        request = _complete_oidc_login(
            {"sub": "oidc-uid", "email": "user@example.com", "email_verified": True}
        )

        self.assertEqual(request.session.get(SESSION_KEY), str(self.user.pk))
        self.assertEqual(request.session.get(BACKEND_SESSION_KEY), SOCIAL_ONLY_BACKEND)

    def test_permission_checks_still_work(self):
        member = get_user_model().objects.create_user(
            email="member@example.com", password="member-password"
        )
        member.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="accounts", codename="view_account"
            )
        )
        member = get_user_model().objects.get(pk=member.pk)

        self.assertTrue(member.has_perm("accounts.view_account"))
        self.assertFalse(member.has_perm("accounts.delete_account"))
