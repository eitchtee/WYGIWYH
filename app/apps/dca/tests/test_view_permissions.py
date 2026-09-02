"""Object-level authorization tests for the DCA views.

DCAEntry has an unscoped default manager, so filtering an entry by
``strategy__id`` alone reached entries belonging to strategies the caller could
not see at all -- a strictly wider hole than the one reported for rules in
GHSA-83g9-vjqf-2j5q, since it needs no public or shared strategy.
"""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.currencies.models import Currency
from apps.dca.models import DCAEntry, DCAStrategy

HTMX = {"HTTP_HX_REQUEST": "true"}


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
    WHITENOISE_AUTOREFRESH=True,
    DEMO=False,
)
class DCAObjectPermissionTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="owner@test.com", password="testpass123"
        )
        self.shared_user = User.objects.create_user(
            email="shared@test.com", password="testpass123"
        )
        self.stranger = User.objects.create_user(
            email="stranger@test.com", password="testpass123"
        )
        self.currency = Currency.objects.create(
            code="USD", name="US Dollar", decimal_places=2
        )

        self.private_strategy = self._strategy("Private", visibility="private")
        self.public_strategy = self._strategy("Public", visibility="public")
        self.shared_strategy = self._strategy("Shared", visibility="private")
        self.shared_strategy.shared_with.add(self.shared_user)

        self.private_entry = self._entry(self.private_strategy)
        self.public_entry = self._entry(self.public_strategy)
        self.shared_entry = self._entry(self.shared_strategy)

    def _strategy(self, name, visibility):
        return DCAStrategy.all_objects.create(
            name=name,
            owner=self.owner,
            visibility=visibility,
            target_currency=self.currency,
            payment_currency=self.currency,
        )

    def _entry(self, strategy):
        return DCAEntry.objects.create(
            strategy=strategy,
            date=date(2025, 1, 1),
            amount_paid=Decimal("100"),
            amount_received=Decimal("1"),
        )

    # ------------------------------------------------------------------
    # entries on an invisible strategy: must not even confirm they exist
    # ------------------------------------------------------------------
    def test_stranger_cannot_delete_entry_on_private_strategy(self):
        self.client.force_login(self.stranger)

        response = self.client.delete(
            reverse(
                "dca_entry_delete",
                kwargs={
                    "strategy_id": self.private_strategy.id,
                    "entry_id": self.private_entry.id,
                },
            ),
            **HTMX,
        )

        self.assertEqual(response.status_code, 404)
        self.assertTrue(DCAEntry.objects.filter(pk=self.private_entry.pk).exists())

    def test_stranger_cannot_open_entry_edit_form_on_private_strategy(self):
        self.client.force_login(self.stranger)

        response = self.client.get(
            reverse(
                "dca_entry_edit",
                kwargs={
                    "strategy_id": self.private_strategy.id,
                    "entry_id": self.private_entry.id,
                },
            ),
            **HTMX,
        )

        self.assertEqual(response.status_code, 404)

    def test_stranger_cannot_edit_entry_on_private_strategy(self):
        self.client.force_login(self.stranger)

        response = self.client.post(
            reverse(
                "dca_entry_edit",
                kwargs={
                    "strategy_id": self.private_strategy.id,
                    "entry_id": self.private_entry.id,
                },
            ),
            data={
                "date": "2030-01-01",
                "amount_paid": "999",
                "amount_received": "999",
            },
            **HTMX,
        )

        self.assertEqual(response.status_code, 404)
        self.private_entry.refresh_from_db()
        self.assertEqual(self.private_entry.amount_paid, Decimal("100"))

    # ------------------------------------------------------------------
    # entries on a visible-but-unowned strategy: 403, not 404
    # ------------------------------------------------------------------
    def test_stranger_cannot_delete_entry_on_public_strategy(self):
        self.client.force_login(self.stranger)

        response = self.client.delete(
            reverse(
                "dca_entry_delete",
                kwargs={
                    "strategy_id": self.public_strategy.id,
                    "entry_id": self.public_entry.id,
                },
            ),
            **HTMX,
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(DCAEntry.objects.filter(pk=self.public_entry.pk).exists())

    def test_shared_user_cannot_add_entry_to_shared_strategy(self):
        self.client.force_login(self.shared_user)

        response = self.client.post(
            reverse("dca_entry_add", kwargs={"strategy_id": self.shared_strategy.id}),
            data={
                "date": "2030-01-01",
                "amount_paid": "5",
                "amount_received": "5",
            },
            **HTMX,
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.shared_strategy.entries.count(), 1)

    def test_owner_can_still_manage_own_entries(self):
        self.client.force_login(self.owner)

        response = self.client.delete(
            reverse(
                "dca_entry_delete",
                kwargs={
                    "strategy_id": self.private_strategy.id,
                    "entry_id": self.private_entry.id,
                },
            ),
            **HTMX,
        )

        self.assertEqual(response.status_code, 204)
        self.assertFalse(DCAEntry.objects.filter(pk=self.private_entry.pk).exists())

    # ------------------------------------------------------------------
    # reads stay open to shared users
    # ------------------------------------------------------------------
    def test_shared_user_can_still_view_strategy_detail(self):
        self.client.force_login(self.shared_user)

        response = self.client.get(
            reverse(
                "dca_strategy_detail", kwargs={"strategy_id": self.shared_strategy.id}
            ),
            **HTMX,
        )

        self.assertEqual(response.status_code, 200)

    # ------------------------------------------------------------------
    # strategy delete: the same inversion the rules views had
    # ------------------------------------------------------------------
    def test_stranger_cannot_delete_public_strategy(self):
        self.client.force_login(self.stranger)

        response = self.client.delete(
            reverse(
                "dca_strategy_delete", kwargs={"strategy_id": self.public_strategy.id}
            ),
            **HTMX,
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(
            DCAStrategy.all_objects.filter(pk=self.public_strategy.pk).exists()
        )

    def test_shared_user_deleting_only_revokes_their_own_access(self):
        self.client.force_login(self.shared_user)

        response = self.client.delete(
            reverse(
                "dca_strategy_delete", kwargs={"strategy_id": self.shared_strategy.id}
            ),
            **HTMX,
        )

        self.assertEqual(response.status_code, 204)
        self.assertTrue(
            DCAStrategy.all_objects.filter(pk=self.shared_strategy.pk).exists()
        )
        self.assertNotIn(self.shared_user, self.shared_strategy.shared_with.all())

    def test_owner_can_delete_own_strategy(self):
        self.client.force_login(self.owner)

        response = self.client.delete(
            reverse(
                "dca_strategy_delete", kwargs={"strategy_id": self.public_strategy.id}
            ),
            **HTMX,
        )

        self.assertEqual(response.status_code, 204)
        self.assertFalse(
            DCAStrategy.all_objects.filter(pk=self.public_strategy.pk).exists()
        )
