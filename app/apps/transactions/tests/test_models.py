import datetime
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.transactions.models import (
    TransactionCategory,
    TransactionTag,
    Transaction,
    InstallmentPlan,
    RecurringTransaction,
)
from apps.accounts.models import Account, AccountGroup
from apps.currencies.models import Currency, ExchangeRate


class TransactionCategoryTests(TestCase):
    def test_category_creation(self):
        """Test basic category creation"""
        category = TransactionCategory.objects.create(name="Groceries")
        self.assertEqual(str(category), "Groceries")
        self.assertFalse(category.mute)


class TransactionTagTests(TestCase):
    def test_tag_creation(self):
        """Test basic tag creation"""
        tag = TransactionTag.objects.create(name="Essential")
        self.assertEqual(str(tag), "Essential")


class TransactionTests(TestCase):
    def setUp(self):
        """Set up test data"""
        self.currency = Currency.objects.create(
            code="USD", name="US Dollar", decimal_places=2, prefix="$ "
        )
        self.account_group = AccountGroup.objects.create(name="Test Group")
        self.account = Account.objects.create(
            name="Test Account", group=self.account_group, currency=self.currency
        )
        self.category = TransactionCategory.objects.create(name="Test Category")

    def test_transaction_creation(self):
        """Test basic transaction creation with required fields"""
        transaction = Transaction.objects.create(
            account=self.account,
            type=Transaction.Type.EXPENSE,
            date=timezone.now().date(),
            amount=Decimal("100.00"),
            description="Test transaction",
        )
        self.assertTrue(transaction.is_paid)
        self.assertEqual(transaction.type, Transaction.Type.EXPENSE)
        self.assertEqual(transaction.account.currency.code, "USD")

    def test_transaction_with_exchange_currency(self):
        """Test transaction with exchange currency"""
        eur = Currency.objects.create(
            code="EUR", name="Euro", decimal_places=2, prefix="€"
        )
        self.account.exchange_currency = eur
        self.account.save()

        # Create exchange rate
        ExchangeRate.objects.create(
            from_currency=self.currency,
            to_currency=eur,
            rate=Decimal("0.85"),
            date=timezone.now(),
        )

        transaction = Transaction.objects.create(
            account=self.account,
            type=Transaction.Type.EXPENSE,
            date=timezone.now().date(),
            amount=Decimal("100.00"),
            description="Test transaction",
        )

        exchanged = transaction.exchanged_amount()
        self.assertIsNotNone(exchanged)
        self.assertEqual(exchanged["prefix"], "€")

    def test_truncating_amount(self):
        """Test amount truncating based on account.currency decimal places"""
        transaction = Transaction.objects.create(
            account=self.account,
            type=Transaction.Type.EXPENSE,
            date=timezone.now().date(),
            amount=Decimal(
                "100.0100001"
            ),  # account currency has two decimal places, the last 1 should be removed
            description="Test transaction",
        )
        self.assertEqual(transaction.amount, Decimal("100.0100000"))

    def test_automatic_reference_date(self):
        """Test reference_date from date"""
        transaction = Transaction.objects.create(
            account=self.account,
            type=Transaction.Type.EXPENSE,
            date=datetime.datetime(day=20, month=1, year=2000).date(),
            amount=Decimal("100"),
            description="Test transaction",
        )
        self.assertEqual(
            transaction.reference_date,
            datetime.datetime(day=1, month=1, year=2000).date(),
        )

    def test_reference_date_is_always_on_first_day(self):
        """Test reference_date is always on the first day"""
        transaction = Transaction.objects.create(
            account=self.account,
            type=Transaction.Type.EXPENSE,
            date=datetime.datetime(day=20, month=1, year=2000).date(),
            reference_date=datetime.datetime(day=20, month=2, year=2000).date(),
            amount=Decimal("100"),
            description="Test transaction",
        )
        self.assertEqual(
            transaction.reference_date,
            datetime.datetime(day=1, month=2, year=2000).date(),
        )


class InstallmentPlanTests(TestCase):
    def setUp(self):
        """Set up test data"""
        self.currency = Currency.objects.create(
            code="USD", name="US Dollar", decimal_places=2, prefix="$ "
        )
        self.account = Account.objects.create(
            name="Test Account", currency=self.currency
        )

    def test_installment_plan_creation(self):
        """Test basic installment plan creation"""
        plan = InstallmentPlan.objects.create(
            account=self.account,
            type=Transaction.Type.EXPENSE,
            description="Test Plan",
            number_of_installments=12,
            start_date=timezone.now().date(),
            installment_amount=Decimal("100.00"),
            recurrence=InstallmentPlan.Recurrence.MONTHLY,
        )
        self.assertEqual(plan.number_of_installments, 12)
        self.assertEqual(plan.installment_start, 1)
        self.assertEqual(plan.account.currency.code, "USD")


class RecurringTransactionTests(TestCase):
    def setUp(self):
        """Set up test data"""
        self.currency = Currency.objects.create(
            code="USD", name="US Dollar", decimal_places=2, prefix="$ "
        )
        self.account = Account.objects.create(
            name="Test Account", currency=self.currency
        )

    def test_recurring_transaction_creation(self):
        """Test basic recurring transaction creation"""
        recurring = RecurringTransaction.objects.create(
            account=self.account,
            type=Transaction.Type.EXPENSE,
            amount=Decimal("100.00"),
            description="Monthly Payment",
            start_date=timezone.now().date(),
            recurrence_type=RecurringTransaction.RecurrenceType.MONTH,
            recurrence_interval=1,
        )
        self.assertFalse(recurring.is_paused)
        self.assertEqual(recurring.recurrence_interval, 1)
        self.assertEqual(recurring.account.currency.code, "USD")
