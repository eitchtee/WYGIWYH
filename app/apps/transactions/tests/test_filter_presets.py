from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.transactions.models import FilterPreset


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
    WHITENOISE_AUTOREFRESH=True,
)
class FilterPresetViewTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            email="preset-owner@example.com", password="testpass123"
        )
        self.other_user = user_model.objects.create_user(
            email="other-user@example.com", password="testpass123"
        )
        self.client.force_login(self.user)
        self.preset = FilterPreset.objects.create(
            owner=self.user,
            name="Unpaid",
            parameters={"is_paid": ["0"], "type": ["IN", "EX"]},
        )

    def test_create_stores_only_transaction_filter_fields(self):
        response = self.client.post(
            reverse("filter_preset_create"),
            {
                "name": "Account X Unpaid",
                "account": ["Account X"],
                "is_paid": ["0"],
                "order": "newer",
            },
            HTTP_HX_REQUEST="true",
        )

        preset = FilterPreset.objects.get(
            owner=self.user, name="Account X Unpaid"
        )
        self.assertEqual(
            preset.parameters,
            {"account": ["Account X"], "is_paid": ["0"]},
        )
        self.assertContains(response, "Account X Unpaid")

    def test_create_rejects_a_blank_name(self):
        response = self.client.post(
            reverse("filter_preset_create"),
            {"name": "   ", "is_paid": ["0"]},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(FilterPreset.objects.filter(owner=self.user).count(), 1)

    def test_apply_returns_the_saved_filter_form_without_changing_the_url(self):
        response = self.client.get(
            reverse("filter_preset_apply", args=[self.preset.pk]),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="filter"')
        self.assertEqual(response.context["filter"].data.getlist("is_paid"), ["0"])
        self.assertEqual(
            response.context["filter"].data.getlist("type"), ["IN", "EX"]
        )
        self.assertNotIn("HX-Push-Url", response.headers)
        self.assertNotIn("HX-Replace-Url", response.headers)
        self.assertIs(response.context.get("filter_is_active"), True)
        self.assertContains(response, 'hx-swap-oob="outerHTML"')
        self.assertEqual(
            response.headers["HX-Trigger-After-Settle"],
            "updated",
        )

    def test_clear_returns_the_default_filter_form_without_changing_the_url(self):
        response = self.client.get(
            "/transactions/filter/clear/",
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="filter"')
        self.assertEqual(
            response.context["filter"].data.getlist("type"), ["IN", "EX"]
        )
        self.assertEqual(
            response.context["filter"].data.getlist("is_paid"), ["1", "0"]
        )
        self.assertNotIn("HX-Push-Url", response.headers)
        self.assertNotIn("HX-Replace-Url", response.headers)
        self.assertIs(response.context.get("filter_is_active"), False)
        self.assertContains(response, 'hx-swap-oob="outerHTML"')
        self.assertEqual(
            response.headers["HX-Trigger-After-Settle"],
            "updated",
        )

    def test_other_users_cannot_apply_or_delete_a_preset(self):
        self.client.force_login(self.other_user)

        apply_response = self.client.get(
            reverse("filter_preset_apply", args=[self.preset.pk]),
            HTTP_HX_REQUEST="true",
        )
        delete_response = self.client.post(
            reverse("filter_preset_delete", args=[self.preset.pk]),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(apply_response.status_code, 404)
        self.assertEqual(delete_response.status_code, 404)
        self.assertTrue(FilterPreset.objects.filter(pk=self.preset.pk).exists())

    def test_delete_removes_the_current_users_preset(self):
        response = self.client.post(
            reverse("filter_preset_delete", args=[self.preset.pk]),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(FilterPreset.objects.filter(pk=self.preset.pk).exists())
        self.assertNotContains(response, self.preset.name)

    def test_all_transactions_page_only_offers_the_current_users_presets(self):
        FilterPreset.objects.create(
            owner=self.other_user,
            name="Other User Preset",
            parameters={"type": ["IN"]},
        )

        response = self.client.get(reverse("transactions_all_index"))

        self.assertContains(response, self.preset.name)
        self.assertNotContains(response, "Other User Preset")
        self.assertContains(response, 'id="filter-presets"')
        self.assertNotContains(response, 'href="./?')
        self.assertContains(
            response,
            reverse("filter_preset_apply", args=[self.preset.pk]),
        )

    def test_all_transactions_page_marks_a_filtered_query_active(self):
        response = self.client.get(
            reverse("transactions_all_index"),
            {"type": ["IN", "EX"], "is_paid": ["0"]},
        )

        self.assertIs(response.context["filter_is_active"], True)

    def test_all_transactions_page_does_not_mark_default_query_active(self):
        response = self.client.get(
            reverse("transactions_all_index"),
            {
                "type": ["IN", "EX"],
                "is_paid": ["1", "0"],
                "mute_status": ["active", "muted"],
            },
        )

        self.assertIs(response.context["filter_is_active"], False)

    def test_monthly_page_renders_preset_controls(self):
        other_preset = FilterPreset.objects.create(
            owner=self.other_user,
            name="Other Monthly Preset",
            parameters={"type": ["IN"]},
        )
        response = self.client.get(reverse("monthly_overview", args=[8, 2026]))

        self.assertContains(response, 'id="filter-presets"')
        self.assertNotContains(response, 'href="./?')
        self.assertContains(response, reverse("filter_preset_create"))
        self.assertNotContains(response, other_preset.name)
