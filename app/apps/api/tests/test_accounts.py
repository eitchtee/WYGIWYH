from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account, AccountGroup
from apps.currencies.models import Currency
from apps.transactions.models import Transaction


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
    WHITENOISE_AUTOREFRESH=True,
)
class AccountBalanceAPITests(TestCase):
    """Tests for the Account Balance API endpoint"""

    def setUp(self):
        """Set up test data"""
        User = get_user_model()
        self.user = User.objects.create_user(
            email="testuser@test.com", password="testpass123"
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.currency = Currency.objects.create(
            code="USD", name="US Dollar", decimal_places=2, prefix="$ "
        )
        self.account_group = AccountGroup.objects.create(name="Test Group")
        self.account = Account.objects.create(
            name="Test Account", group=self.account_group, currency=self.currency
        )

        # Create some transactions
        Transaction.objects.create(
            account=self.account,
            type=Transaction.Type.INCOME,
            amount=Decimal("500.00"),
            is_paid=True,
            date=date(2025, 1, 1),
            description="Paid income",
        )
        Transaction.objects.create(
            account=self.account,
            type=Transaction.Type.INCOME,
            amount=Decimal("200.00"),
            is_paid=False,
            date=date(2025, 1, 15),
            description="Unpaid income",
        )
        Transaction.objects.create(
            account=self.account,
            type=Transaction.Type.EXPENSE,
            amount=Decimal("100.00"),
            is_paid=True,
            date=date(2025, 1, 10),
            description="Paid expense",
        )

    def test_get_balance_success(self):
        """Test successful balance retrieval"""
        response = self.client.get(f"/api/accounts/{self.account.id}/balance/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("current_balance", response.data)
        self.assertIn("projected_balance", response.data)
        self.assertIn("currency", response.data)

        # Current: 500 - 100 = 400
        self.assertEqual(Decimal(response.data["current_balance"]), Decimal("400.00"))
        # Projected: (500 + 200) - 100 = 600
        self.assertEqual(Decimal(response.data["projected_balance"]), Decimal("600.00"))

        # Check currency data
        self.assertEqual(response.data["currency"]["code"], "USD")

    def test_get_balance_nonexistent_account(self):
        """Test balance for non-existent account returns 404"""
        response = self.client.get("/api/accounts/99999/balance/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_balance_unauthenticated(self):
        """Test unauthenticated request returns 403"""
        unauthenticated_client = APIClient()
        response = unauthenticated_client.get(
            f"/api/accounts/{self.account.id}/balance/"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
