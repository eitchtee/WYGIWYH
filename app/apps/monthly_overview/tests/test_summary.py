from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.accounts.models import Account, AccountGroup
from apps.currencies.models import Currency
from apps.transactions.models import (
    Transaction,
    TransactionCategory,
    TransactionTag,
)


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
    WHITENOISE_AUTOREFRESH=True,
)
class MonthlySummaryFilterBehaviorTests(TestCase):
    """Tests for monthly summary views filter behavior.

    These tests verify that:
    1. Views work correctly without any filters
    2. Views work correctly with filters applied
    3. The filter detection logic properly uses different querysets
    4. Calculated values reflect the applied filters
    """

    def setUp(self):
        """Set up test data"""
        User = get_user_model()
        self.user = User.objects.create_user(
            email="testuser@test.com", password="testpass123"
        )
        self.client.login(username="testuser@test.com", password="testpass123")

        self.currency = Currency.objects.create(
            code="USD", name="US Dollar", decimal_places=2, prefix="$ "
        )
        self.account_group = AccountGroup.objects.create(name="Test Group")
        self.account = Account.objects.create(
            name="Test Account",
            group=self.account_group,
            currency=self.currency,
            is_asset=False,
        )
        self.category = TransactionCategory.objects.create(
            name="Test Category", owner=self.user
        )
        self.tag = TransactionTag.objects.create(name="TestTag", owner=self.user)

        # Create test transactions for December 2025
        # Income: 1000 (paid)
        self.income_transaction = Transaction.objects.create(
            account=self.account,
            type=Transaction.Type.INCOME,
            is_paid=True,
            date=date(2025, 12, 10),
            reference_date=date(2025, 12, 1),
            amount=Decimal("1000.00"),
            description="December Income",
            owner=self.user,
        )

        # Expense: 200 (paid)
        self.expense_transaction = Transaction.objects.create(
            account=self.account,
            type=Transaction.Type.EXPENSE,
            is_paid=True,
            date=date(2025, 12, 15),
            reference_date=date(2025, 12, 1),
            amount=Decimal("200.00"),
            description="December Expense",
            category=self.category,
            owner=self.user,
        )
        self.expense_transaction.tags.add(self.tag)

        # Expense: 150 (projected/unpaid)
        self.projected_expense = Transaction.objects.create(
            account=self.account,
            type=Transaction.Type.EXPENSE,
            is_paid=False,
            date=date(2025, 12, 20),
            reference_date=date(2025, 12, 1),
            amount=Decimal("150.00"),
            description="Projected Expense",
            owner=self.user,
        )

    def _get_currency_data(self, context_dict):
        """Helper to extract data for our test currency from context dict.

        The context dict is keyed by currency ID, so we need to find
        the entry for our currency.
        """
        if not context_dict:
            return None
        for currency_id, data in context_dict.items():
            if data.get("currency", {}).get("code") == "USD":
                return data
        return None

    # --- monthly_summary view tests ---

    def test_monthly_summary_no_filter_returns_200(self):
        """Test that monthly_summary returns 200 without filters"""
        response = self.client.get(
            "/monthly/12/2025/summary/",
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)

    def test_monthly_summary_no_filter_includes_all_transactions(self):
        """Without filters, summary should include all transactions"""
        response = self.client.get(
            "/monthly/12/2025/summary/",
            HTTP_HX_REQUEST="true",
        )
        context = response.context

        # income_current should have the income: 1000
        income_current = context.get("income_current", {})
        usd_data = self._get_currency_data(income_current)
        self.assertIsNotNone(usd_data)
        self.assertEqual(usd_data["income_current"], Decimal("1000.00"))

        # expense_current should have paid expense: 200
        expense_current = context.get("expense_current", {})
        usd_data = self._get_currency_data(expense_current)
        self.assertIsNotNone(usd_data)
        self.assertEqual(usd_data["expense_current"], Decimal("200.00"))

        # expense_projected should have unpaid expense: 150
        expense_projected = context.get("expense_projected", {})
        usd_data = self._get_currency_data(expense_projected)
        self.assertIsNotNone(usd_data)
        self.assertEqual(usd_data["expense_projected"], Decimal("150.00"))

    def test_monthly_summary_type_filter_only_income(self):
        """With type=IN filter, summary should only include income"""
        response = self.client.get(
            "/monthly/12/2025/summary/?type=IN",
            HTTP_HX_REQUEST="true",
        )
        context = response.context

        # income_current should still have 1000
        income_current = context.get("income_current", {})
        usd_data = self._get_currency_data(income_current)
        self.assertIsNotNone(usd_data)
        self.assertEqual(usd_data["income_current"], Decimal("1000.00"))

        # expense_current should be empty/zero (filtered out)
        expense_current = context.get("expense_current", {})
        usd_data = self._get_currency_data(expense_current)
        if usd_data:
            self.assertEqual(usd_data.get("expense_current", 0), Decimal("0"))

        # expense_projected should be empty/zero (filtered out)
        expense_projected = context.get("expense_projected", {})
        usd_data = self._get_currency_data(expense_projected)
        if usd_data:
            self.assertEqual(usd_data.get("expense_projected", 0), Decimal("0"))

    def test_monthly_summary_type_filter_only_expenses(self):
        """With type=EX filter, summary should only include expenses"""
        response = self.client.get(
            "/monthly/12/2025/summary/?type=EX",
            HTTP_HX_REQUEST="true",
        )
        context = response.context

        # income_current should be empty/zero (filtered out)
        income_current = context.get("income_current", {})
        usd_data = self._get_currency_data(income_current)
        if usd_data:
            self.assertEqual(usd_data.get("income_current", 0), Decimal("0"))

        # expense_current should have 200
        expense_current = context.get("expense_current", {})
        usd_data = self._get_currency_data(expense_current)
        self.assertIsNotNone(usd_data)
        self.assertEqual(usd_data["expense_current"], Decimal("200.00"))

        # expense_projected should have 150
        expense_projected = context.get("expense_projected", {})
        usd_data = self._get_currency_data(expense_projected)
        self.assertIsNotNone(usd_data)
        self.assertEqual(usd_data["expense_projected"], Decimal("150.00"))

    def test_monthly_summary_is_paid_filter_only_paid(self):
        """With is_paid=1 filter, summary should only include paid transactions"""
        response = self.client.get(
            "/monthly/12/2025/summary/?is_paid=1",
            HTTP_HX_REQUEST="true",
        )
        context = response.context

        # income_current should have 1000 (paid)
        income_current = context.get("income_current", {})
        usd_data = self._get_currency_data(income_current)
        self.assertIsNotNone(usd_data)
        self.assertEqual(usd_data["income_current"], Decimal("1000.00"))

        # expense_current should have 200 (paid)
        expense_current = context.get("expense_current", {})
        usd_data = self._get_currency_data(expense_current)
        self.assertIsNotNone(usd_data)
        self.assertEqual(usd_data["expense_current"], Decimal("200.00"))

        # expense_projected should be empty/zero (filtered out - unpaid)
        expense_projected = context.get("expense_projected", {})
        usd_data = self._get_currency_data(expense_projected)
        if usd_data:
            self.assertEqual(usd_data.get("expense_projected", 0), Decimal("0"))

    def test_monthly_summary_is_paid_filter_only_unpaid(self):
        """With is_paid=0 filter, summary should only include unpaid transactions"""
        response = self.client.get(
            "/monthly/12/2025/summary/?is_paid=0",
            HTTP_HX_REQUEST="true",
        )
        context = response.context

        # income_current should be empty/zero (filtered out - paid)
        income_current = context.get("income_current", {})
        usd_data = self._get_currency_data(income_current)
        if usd_data:
            self.assertEqual(usd_data.get("income_current", 0), Decimal("0"))

        # expense_current should be empty/zero (filtered out - paid)
        expense_current = context.get("expense_current", {})
        usd_data = self._get_currency_data(expense_current)
        if usd_data:
            self.assertEqual(usd_data.get("expense_current", 0), Decimal("0"))

        # expense_projected should have 150 (unpaid)
        expense_projected = context.get("expense_projected", {})
        usd_data = self._get_currency_data(expense_projected)
        self.assertIsNotNone(usd_data)
        self.assertEqual(usd_data["expense_projected"], Decimal("150.00"))

    def test_monthly_summary_description_filter(self):
        """With description filter, summary should only include matching transactions"""
        response = self.client.get(
            "/monthly/12/2025/summary/?description=Income",
            HTTP_HX_REQUEST="true",
        )
        context = response.context

        # Only income matches "Income" description
        income_current = context.get("income_current", {})
        usd_data = self._get_currency_data(income_current)
        self.assertIsNotNone(usd_data)
        self.assertEqual(usd_data["income_current"], Decimal("1000.00"))

        # Expenses should be filtered out
        expense_current = context.get("expense_current", {})
        usd_data = self._get_currency_data(expense_current)
        if usd_data:
            self.assertEqual(usd_data.get("expense_current", 0), Decimal("0"))

    def test_monthly_summary_amount_filter(self):
        """With amount filter, summary should only include transactions in range"""
        # Filter to only get transactions between 100 and 250 (should get 200 and 150)
        response = self.client.get(
            "/monthly/12/2025/summary/?from_amount=100&to_amount=250",
            HTTP_HX_REQUEST="true",
        )
        context = response.context

        # Income (1000) should be filtered out
        income_current = context.get("income_current", {})
        usd_data = self._get_currency_data(income_current)
        if usd_data:
            self.assertEqual(usd_data.get("income_current", 0), Decimal("0"))

        # expense_current should have 200
        expense_current = context.get("expense_current", {})
        usd_data = self._get_currency_data(expense_current)
        self.assertIsNotNone(usd_data)
        self.assertEqual(usd_data["expense_current"], Decimal("200.00"))

        # expense_projected should have 150
        expense_projected = context.get("expense_projected", {})
        usd_data = self._get_currency_data(expense_projected)
        self.assertIsNotNone(usd_data)
        self.assertEqual(usd_data["expense_projected"], Decimal("150.00"))

    # --- monthly_account_summary view tests ---

    def test_monthly_account_summary_no_filter_returns_200(self):
        """Test that monthly_account_summary returns 200 without filters"""
        response = self.client.get(
            "/monthly/12/2025/summary/accounts/",
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)

    def test_monthly_account_summary_with_filter_returns_200(self):
        """Test that monthly_account_summary returns 200 with filter"""
        response = self.client.get(
            "/monthly/12/2025/summary/accounts/?type=IN",
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)

    # --- monthly_currency_summary view tests ---

    def test_monthly_currency_summary_no_filter_returns_200(self):
        """Test that monthly_currency_summary returns 200 without filters"""
        response = self.client.get(
            "/monthly/12/2025/summary/currencies/",
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)

    def test_monthly_currency_summary_with_filter_returns_200(self):
        """Test that monthly_currency_summary returns 200 with filter"""
        response = self.client.get(
            "/monthly/12/2025/summary/currencies/?type=EX",
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
