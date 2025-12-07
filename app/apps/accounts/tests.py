from datetime import date

from django.test import TestCase

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

