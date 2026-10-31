from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Account, AccountGroup
from apps.currencies.models import Currency


class AccountTests(TestCase):
    def setUp(self):
        """Set up test data"""
        self.currency = Currency.objects.create(
            code="USD", name="US Dollar", decimal_places=2, prefix="$ "
        )
        self.exchange_currency = Currency.objects.create(
            code="EUR", name="Euro", decimal_places=2, prefix="€ "
        )
        self.account_group = AccountGroup.objects.create(name="Test Group")

    def test_account_creation(self):
        """Test basic account creation"""
        account = Account.objects.create(
            name="Test Account",
            group=self.account_group,
            currency=self.currency,
            is_asset=False,
            is_archived=False,
        )
        self.assertEqual(str(account), "Test Account")
        self.assertEqual(account.name, "Test Account")
        self.assertEqual(account.group, self.account_group)
        self.assertEqual(account.currency, self.currency)
        self.assertFalse(account.is_asset)
        self.assertFalse(account.is_archived)

    def test_account_with_exchange_currency(self):
        """Test account creation with exchange currency"""
        account = Account.objects.create(
            name="Exchange Account",
            currency=self.currency,
            exchange_currency=self.exchange_currency,
        )
        self.assertEqual(account.exchange_currency, self.exchange_currency)


class GetAccountBalanceServiceTests(TestCase):
    """Tests for the get_account_balance service function"""

    def setUp(self):
        """Set up test data"""
        from apps.transactions.models import Transaction
        self.Transaction = Transaction
        
        self.currency = Currency.objects.create(
            code="BRL", name="Brazilian Real", decimal_places=2, prefix="R$ "
        )
        self.account_group = AccountGroup.objects.create(name="Service Test Group")
        self.account = Account.objects.create(
            name="Service Test Account", group=self.account_group, currency=self.currency
        )

    def test_balance_with_no_transactions(self):
        """Test balance is 0 when no transactions exist"""
        from apps.accounts.services import get_account_balance
        from decimal import Decimal
        
        balance = get_account_balance(self.account, paid_only=True)
        self.assertEqual(balance, Decimal("0"))

    def test_current_balance_only_counts_paid(self):
        """Test current balance only counts paid transactions"""
        from apps.accounts.services import get_account_balance
        from decimal import Decimal
        
        # Paid income
        self.Transaction.objects.create(
            account=self.account,
            type=self.Transaction.Type.INCOME,
            amount=Decimal("100.00"),
            is_paid=True,
            date=date(2025, 1, 1),
            description="Paid income",
        )
        # Unpaid income (should not count)
        self.Transaction.objects.create(
            account=self.account,
            type=self.Transaction.Type.INCOME,
            amount=Decimal("50.00"),
            is_paid=False,
            date=date(2025, 1, 1),
            description="Unpaid income",
        )
        # Paid expense
        self.Transaction.objects.create(
            account=self.account,
            type=self.Transaction.Type.EXPENSE,
            amount=Decimal("30.00"),
            is_paid=True,
            date=date(2025, 1, 1),
            description="Paid expense",
        )

        balance = get_account_balance(self.account, paid_only=True)
        self.assertEqual(balance, Decimal("70.00"))  # 100 - 30

    def test_projected_balance_counts_all(self):
        """Test projected balance counts all transactions"""
        from apps.accounts.services import get_account_balance
        from decimal import Decimal
        
        # Paid income
        self.Transaction.objects.create(
            account=self.account,
            type=self.Transaction.Type.INCOME,
            amount=Decimal("100.00"),
            is_paid=True,
            date=date(2025, 1, 1),
            description="Paid income",
        )
        # Unpaid income
        self.Transaction.objects.create(
            account=self.account,
            type=self.Transaction.Type.INCOME,
            amount=Decimal("50.00"),
            is_paid=False,
            date=date(2025, 1, 1),
            description="Unpaid income",
        )
        # Paid expense
        self.Transaction.objects.create(
            account=self.account,
            type=self.Transaction.Type.EXPENSE,
            amount=Decimal("30.00"),
            is_paid=True,
            date=date(2025, 1, 1),
            description="Paid expense",
        )
        # Unpaid expense
        self.Transaction.objects.create(
            account=self.account,
            type=self.Transaction.Type.EXPENSE,
            amount=Decimal("20.00"),
            is_paid=False,
            date=date(2025, 1, 1),
            description="Unpaid expense",
        )

        balance = get_account_balance(self.account, paid_only=False)
        self.assertEqual(balance, Decimal("100.00"))  # (100 + 50) - (30 + 20)

    def test_balance_defaults_to_paid_only(self):
        """Test that paid_only defaults to True"""
        from apps.accounts.services import get_account_balance
        from decimal import Decimal
        
        self.Transaction.objects.create(
            account=self.account,
            type=self.Transaction.Type.INCOME,
            amount=Decimal("100.00"),
            is_paid=True,
            date=date(2025, 1, 1),
            description="Paid",
        )
        self.Transaction.objects.create(
            account=self.account,
            type=self.Transaction.Type.INCOME,
            amount=Decimal("50.00"),
            is_paid=False,
            date=date(2025, 1, 1),
            description="Unpaid",
        )

        balance = get_account_balance(self.account)  # defaults to paid_only=True
        self.assertEqual(balance, Decimal("100.00"))



class GetAccountBalanceCutoffTests(TestCase):
    """get_account_balance with date / reference month cutoffs."""

    def setUp(self):
        from apps.transactions.models import Transaction

        self.Transaction = Transaction
        currency = Currency.objects.create(code="BRL", name="Real", decimal_places=2)
        self.account = Account.objects.create(name="Card", currency=currency)
        # Paid expenses: Oct 10 (ref Oct), Oct 20 (ref Nov), Nov 5 (ref Nov)
        for day, ref, amount in [
            (date(2026, 10, 10), date(2026, 10, 1), "10"),
            (date(2026, 10, 20), date(2026, 11, 1), "20"),
            (date(2026, 11, 5), date(2026, 11, 1), "40"),
        ]:
            Transaction.objects.create(
                account=self.account,
                type=Transaction.Type.EXPENSE,
                amount=Decimal(amount),
                is_paid=True,
                date=day,
                reference_date=ref,
                description="x",
            )

    def test_date_cutoff(self):
        from apps.accounts.services import get_account_balance

        self.assertEqual(
            get_account_balance(self.account, date_lte=date(2026, 10, 20)),
            Decimal("-30"),
        )

    def test_reference_month_cutoff(self):
        from apps.accounts.services import get_account_balance

        self.assertEqual(
            get_account_balance(self.account, reference_date_lte=date(2026, 10, 1)),
            Decimal("-10"),
        )

    def test_no_cutoff_counts_everything_paid(self):
        from apps.accounts.services import get_account_balance

        self.assertEqual(get_account_balance(self.account), Decimal("-70"))


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
    WHITENOISE_AUTOREFRESH=True,
)
class AccountReconciliationCutoffViewTests(TestCase):
    HTMX = {"HTTP_HX_REQUEST": "true"}

    def setUp(self):
        from apps.transactions.models import Transaction

        self.Transaction = Transaction
        self.user = get_user_model().objects.create_user(
            email="u@test.com", password="testpass123"
        )
        self.client.force_login(self.user)
        currency = Currency.objects.create(code="BRL", name="Real", decimal_places=2)
        self.account = Account.objects.create(
            name="Card", currency=currency, owner=self.user
        )
        for day, ref, amount in [
            (date(2026, 10, 10), date(2026, 10, 1), "10"),
            (date(2026, 12, 5), date(2026, 12, 1), "40"),  # paid, in the future
        ]:
            Transaction.objects.create(
                account=self.account,
                type=Transaction.Type.EXPENSE,
                amount=Decimal(amount),
                is_paid=True,
                date=day,
                reference_date=ref,
                description="x",
                owner=self.user,
            )
        self.url = reverse("account_reconciliation")

    def post(self, cutoff, new_balance):
        return self.client.post(
            self.url,
            {
                **cutoff,
                "form-TOTAL_FORMS": "1",
                "form-INITIAL_FORMS": "1",
                "form-0-account_id": str(self.account.id),
                "form-0-new_balance": new_balance,
            },
            **self.HTMX,
        )

    def adjustment(self):
        return self.Transaction.objects.get(
            account=self.account, description="Balance reconciliation"
        )

    def test_get_shows_balance_for_month_cutoff(self):
        response = self.client.get(
            self.url,
            {"cutoff-mode": "month", "cutoff-month": "September 2026"},
            **self.HTMX,
        )
        self.assertEqual(response.status_code, 200)
        # The current-month fallback would give -10, so 0 proves the month was read.
        self.assertEqual(response.context["form"].forms[0].current_balance, 0)

    def test_post_date_cutoff_dates_adjustment_at_cutoff(self):
        response = self.post(
            {"cutoff-mode": "date", "cutoff-date": "2026-10-15"}, "-25"
        )
        self.assertEqual(response.status_code, 204)
        adj = self.adjustment()
        # Balance up to Oct 15 is -10, so -15 more is needed.
        self.assertEqual(adj.type, self.Transaction.Type.EXPENSE)
        self.assertEqual(adj.amount, Decimal("15"))
        self.assertEqual(adj.date, date(2026, 10, 15))
        self.assertEqual(adj.reference_date, date(2026, 10, 1))

    def test_post_month_cutoff_dates_adjustment_in_month(self):
        self.post({"cutoff-mode": "month", "cutoff-month": "September 2026"}, "5")
        adj = self.adjustment()
        self.assertEqual(adj.type, self.Transaction.Type.INCOME)
        self.assertEqual(adj.amount, Decimal("5"))
        self.assertEqual(adj.date, date(2026, 9, 30))
        self.assertEqual(adj.reference_date, date(2026, 9, 1))

    def test_post_with_invalid_cutoff_date_does_not_reconcile(self):
        response = self.post({"cutoff-mode": "date", "cutoff-date": "garbage"}, "5")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            self.Transaction.objects.filter(description="Balance reconciliation").exists()
        )

    def test_post_without_cutoff_keeps_current_behavior(self):
        self.post({}, "-50")
        self.assertFalse(
            self.Transaction.objects.filter(description="Balance reconciliation").exists()
        )
