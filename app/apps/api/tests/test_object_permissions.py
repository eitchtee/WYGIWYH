"""Object-level ownership on the SharedObject API viewsets.

DjangoModelPermissions is model-level: a user holding ``change_account`` could
write any object the viewset's queryset returned, and for SharedObject that
queryset includes other people's public and shared-with-them objects. Ordinary
users hold no model permissions, so this was not reachable for them, but the
object-level check was missing entirely.

Reads are unaffected -- they stay governed by SharedObjectManager.
"""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.currencies.models import Currency
from apps.dca.models import DCAEntry, DCAStrategy
from apps.transactions.models import TransactionCategory


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
class SharedObjectAPIPermissionTests(TestCase):
    """The attacker here deliberately HOLDS the Django model permissions.

    Without them DjangoModelPermissions already answers 403 and the
    object-level check is never consulted, so the test would pass whether or
    not it exists.
    """

    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="owner@test.com", password="testpass123"
        )
        self.attacker = User.objects.create_user(
            email="attacker@test.com", password="testpass123"
        )
        self.attacker.user_permissions.set(
            Permission.objects.filter(
                codename__in=[
                    "add_account",
                    "change_account",
                    "delete_account",
                    "add_transactioncategory",
                    "change_transactioncategory",
                    "delete_transactioncategory",
                    "add_dcaentry",
                    "change_dcaentry",
                    "delete_dcaentry",
                ]
            )
        )
        # Permissions are cached on the user instance.
        self.attacker = User.objects.get(pk=self.attacker.pk)

        self.currency = Currency.objects.create(
            code="USD", name="US Dollar", decimal_places=2
        )

        self.api = APIClient()
        self.api.force_authenticate(user=self.attacker)

    def test_cannot_modify_public_account(self):
        account = Account.all_objects.create(
            name="Public account",
            currency=self.currency,
            owner=self.owner,
            visibility="public",
        )

        response = self.api.patch(
            f"/api/accounts/{account.id}/", {"name": "HIJACKED"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        account.refresh_from_db()
        self.assertEqual(account.name, "Public account")

    def test_cannot_delete_account_shared_with_them(self):
        account = Account.all_objects.create(
            name="Shared account",
            currency=self.currency,
            owner=self.owner,
            visibility="private",
        )
        account.shared_with.add(self.attacker)

        response = self.api.delete(f"/api/accounts/{account.id}/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Account.all_objects.filter(pk=account.pk).exists())

    def test_cannot_delete_public_category(self):
        category = TransactionCategory.all_objects.create(
            name="Public category", owner=self.owner, visibility="public"
        )

        response = self.api.delete(f"/api/categories/{category.id}/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(TransactionCategory.all_objects.filter(pk=category.pk).exists())

    def test_cannot_delete_entry_on_public_strategy(self):
        strategy = DCAStrategy.all_objects.create(
            name="Public strategy",
            owner=self.owner,
            visibility="public",
            target_currency=self.currency,
            payment_currency=self.currency,
        )
        entry = DCAEntry.objects.create(
            strategy=strategy,
            date=date(2025, 1, 1),
            amount_paid=Decimal("100"),
            amount_received=Decimal("1"),
        )

        response = self.api.delete(f"/api/dca/entries/{entry.id}/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(DCAEntry.objects.filter(pk=entry.pk).exists())

    def test_reads_of_shared_objects_still_work(self):
        account = Account.all_objects.create(
            name="Public account",
            currency=self.currency,
            owner=self.owner,
            visibility="public",
        )

        response = self.api.get(f"/api/accounts/{account.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_owner_can_still_write_their_own_objects(self):
        owner_client = APIClient()
        self.owner.user_permissions.set(
            Permission.objects.filter(codename__in=["change_account", "delete_account"])
        )
        owner = get_user_model().objects.get(pk=self.owner.pk)
        owner_client.force_authenticate(user=owner)

        account = Account.all_objects.create(
            name="Own account",
            currency=self.currency,
            owner=owner,
            visibility="private",
        )

        response = owner_client.patch(
            f"/api/accounts/{account.id}/", {"name": "Renamed"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        account.refresh_from_db()
        self.assertEqual(account.name, "Renamed")
