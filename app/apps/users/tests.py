from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

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
