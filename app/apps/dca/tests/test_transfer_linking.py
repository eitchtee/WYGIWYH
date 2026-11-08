from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.accounts.models import Account
from apps.common.middleware.thread_local import delete_current_user, write_current_user
from apps.currencies.models import Currency
from apps.dca.forms import DCAEntryForm
from apps.dca.models import DCAStrategy
from apps.transactions.models import Transaction

IN, EX = Transaction.Type.INCOME, Transaction.Type.EXPENSE


class DCATransferLinkingTests(TestCase):
    def setUp(self):
        # Form querysets are scoped to the current user
        write_current_user(get_user_model().objects.create_user(email="d@test.com"))
        self.addCleanup(delete_current_user)
        brl = Currency.objects.create(code="BRL", name="Real", decimal_places=2)
        btc = Currency.objects.create(code="BTC", name="Bitcoin", decimal_places=8)
        self.cash = Account.objects.create(name="Cash", currency=brl)
        self.wallet = Account.objects.create(name="Wallet", currency=btc)
        self.strategy = DCAStrategy.objects.create(
            name="BTC", target_currency=btc, payment_currency=brl
        )

    def tx(self, account, type_, amount):
        return Transaction.objects.create(
            account=account, type=type_, amount=Decimal(amount), date=date(2026, 1, 5)
        )

    def entry_data(self, **extra):
        return {
            "date": "2026-01-05",
            "amount_paid": "500",
            "amount_received": "0.001",
            **extra,
        }

    def test_created_transactions_are_linked(self):
        form = DCAEntryForm(
            data=self.entry_data(
                create_transaction="on",
                from_account=self.cash.id,
                to_account=self.wallet.id,
            ),
            strategy=self.strategy,
        )
        self.assertTrue(form.is_valid(), form.errors)
        entry = form.save()
        self.assertEqual(
            entry.expense_transaction.linked_transaction, entry.income_transaction
        )
        self.assertEqual(
            entry.income_transaction.linked_transaction, entry.expense_transaction
        )

    def test_existing_transactions_are_linked(self):
        expense, income = self.tx(self.cash, EX, "500"), self.tx(self.wallet, IN, "0.001")
        form = DCAEntryForm(
            data=self.entry_data(
                expense_transaction=str(expense.id), income_transaction=str(income.id)
            ),
            strategy=self.strategy,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        expense.refresh_from_db()
        income.refresh_from_db()
        self.assertEqual(expense.linked_transaction, income)
        self.assertEqual(income.linked_transaction, expense)

    def test_transaction_in_another_transfer_is_rejected(self):
        expense, income = self.tx(self.cash, EX, "500"), self.tx(self.wallet, IN, "0.001")
        other = self.tx(self.wallet, IN, "0.002")
        expense.link_transfer(other)
        form = DCAEntryForm(
            data=self.entry_data(
                expense_transaction=str(expense.id), income_transaction=str(income.id)
            ),
            strategy=self.strategy,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("income_transaction", form.errors)

    def test_link_transfer_rules(self):
        expense = self.tx(self.cash, EX, "500")
        with self.assertRaises(ValidationError):
            expense.link_transfer(self.tx(self.cash, IN, "500"))  # same account
        with self.assertRaises(ValidationError):
            expense.link_transfer(self.tx(self.wallet, EX, "1"))  # two expenses
        income = self.tx(self.wallet, IN, "0.001")
        expense.link_transfer(income)
        expense.link_transfer(income)  # already linked to each other: no-op
        self.assertEqual(Transaction.objects.get(pk=income.pk).linked_transaction, expense)
