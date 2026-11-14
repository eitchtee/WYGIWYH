from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase

from apps.accounts.models import Account
from apps.common.middleware.thread_local import write_current_user
from apps.currencies.models import Currency
from apps.rules.models import (
    TransactionRule,
    TransactionRuleAction,
    UpdateOrCreateTransactionRuleAction,
)
from apps.rules.tasks import check_for_transaction_rules
from apps.transactions.models import SubTransaction, Transaction


def run_check_for_transaction_rules_without_worker_wrapper(**kwargs):
    task_func = check_for_transaction_rules.func
    task_func = getattr(task_func, "__wrapped__", task_func)

    return task_func(**kwargs)


class CheckForTransactionRulesTests(TransactionTestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            email="rules@example.com",
            password="testpass123",
        )
        self.currency = Currency.objects.create(
            code="USD",
            name="US Dollar",
            decimal_places=2,
        )
        self.account = Account.objects.create(
            name="Main Account",
            currency=self.currency,
            owner=self.user,
        )

    @patch("apps.rules.signals.check_for_transaction_rules.defer")
    def test_update_or_create_action_can_clear_category_from_none_expression(
        self, mock_defer
    ):
        source_transaction = Transaction.objects.create(
            account=self.account,
            type=Transaction.Type.EXPENSE,
            amount=Decimal("10.00"),
            date=date(2026, 5, 4),
            reference_date=date(2026, 5, 1),
            description="Source without category",
            category=None,
            owner=self.user,
        )
        rule = TransactionRule.objects.create(
            active=True,
            on_create=False,
            on_update=True,
            name="Copy transaction",
            trigger="True",
            owner=self.user,
        )
        UpdateOrCreateTransactionRuleAction.objects.create(
            rule=rule,
            set_account="account_id",
            set_type="'EX'",
            set_date="date",
            set_reference_date="reference_date",
            set_amount="amount",
            set_description="'Generated transaction'",
            set_category="category_name",
        )

        run_check_for_transaction_rules_without_worker_wrapper(
            instance_id=source_transaction.id,
            user_id=self.user.id,
            signal="transaction_updated",
        )

        generated_transaction = Transaction.objects.get(
            description="Generated transaction"
        )
        self.assertIsNone(generated_transaction.category)

    @patch("apps.rules.signals.check_for_transaction_rules.defer")
    def test_update_or_create_action_set_mute_sets_mute_not_is_paid(self, mock_defer):
        source_transaction = Transaction.objects.create(
            account=self.account,
            type=Transaction.Type.EXPENSE,
            amount=Decimal("10.00"),
            date=date(2026, 5, 4),
            reference_date=date(2026, 5, 1),
            description="Unpaid source",
            is_paid=False,
            owner=self.user,
        )
        rule = TransactionRule.objects.create(
            active=True,
            on_create=False,
            on_update=True,
            name="Create muted copy",
            trigger="True",
            owner=self.user,
        )
        UpdateOrCreateTransactionRuleAction.objects.create(
            rule=rule,
            set_account="account_id",
            set_type="'EX'",
            set_date="date",
            set_reference_date="reference_date",
            set_amount="amount",
            set_description="'Muted copy'",
            set_is_paid="is_paid",
            set_mute="True",
        )

        run_check_for_transaction_rules_without_worker_wrapper(
            instance_id=source_transaction.id,
            user_id=self.user.id,
            signal="transaction_updated",
        )

        generated_transaction = Transaction.objects.get(description="Muted copy")
        self.assertTrue(generated_transaction.mute)
        self.assertFalse(generated_transaction.is_paid)

    @patch("apps.rules.signals.check_for_transaction_rules.defer")
    def test_edit_amount_skips_transactions_with_sub_transactions(self, mock_defer):
        rule = TransactionRule.objects.create(
            active=True, on_update=True, name="Set amount", trigger="True", owner=self.user
        )
        TransactionRuleAction.objects.create(rule=rule, field="amount", value="99")
        TransactionRuleAction.objects.create(rule=rule, field="description", value="'Ruled'")
        amounts = {}
        for parts in ([], [Decimal("4"), Decimal("6")]):
            transaction = Transaction.objects.create(
                account=self.account, type=Transaction.Type.EXPENSE, amount=sum(parts) or 1,
                date=date(2026, 5, 4), owner=self.user,
            )
            for amount in parts:
                SubTransaction.objects.create(transaction=transaction, name="Part", amount=amount)
            run_check_for_transaction_rules_without_worker_wrapper(
                instance_id=transaction.id, user_id=self.user.id, signal="transaction_updated"
            )
            transaction.refresh_from_db()
            self.assertEqual(transaction.description, "Ruled")
            amounts[len(parts)] = transaction.amount
        self.assertEqual(amounts, {0: Decimal("99"), 2: Decimal("10")})


class SubTransactionRuleTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(email="subs@example.com", password="x")
        currency = Currency.objects.create(code="USD", name="US Dollar", decimal_places=2)
        self.account = Account.objects.create(name="Main", currency=currency, owner=self.user)
        self.rule = TransactionRule.objects.create(
            active=True, on_update=True, name="Parts", trigger="True", owner=self.user
        )

    def _transaction(self, *parts, amount=None):
        transaction = Transaction.objects.create(
            account=self.account, type=Transaction.Type.EXPENSE, date=date(2026, 5, 4),
            amount=amount if amount is not None else sum(a for _, a in parts), owner=self.user,
        )
        for name, part in parts:
            SubTransaction.objects.create(transaction=transaction, name=name, amount=part)
        return transaction

    def _run(self, transaction):
        with patch("apps.rules.signals.check_for_transaction_rules.defer"):
            run_check_for_transaction_rules_without_worker_wrapper(
                instance_id=transaction.id, user_id=self.user.id, signal="transaction_updated"
            )
        transaction.refresh_from_db()
        return transaction.amount, list(transaction.sub_transactions.values_list("name", "amount"))

    def _edit(self, expression):
        TransactionRuleAction.objects.create(rule=self.rule, field="sub_transactions", value=expression)

    def test_edit_action_adds_changes_and_deletes_parts(self):
        self._edit(
            '[{"name": s["name"], "amount": s["amount"] * 2} for s in sub_transactions'
            ' if s["name"] != "Tip"] + [{"name": "Fee", "amount": decimal("0.50")}]'
        )
        result = self._run(self._transaction(("Meal", Decimal("10")), ("Tip", Decimal("2"))))
        self.assertEqual(result, (Decimal("20.50"), [("Meal", Decimal("20")), ("Fee", Decimal("0.5"))]))

    def test_edit_action_splits_a_plain_transaction_and_clearing_keeps_amount(self):
        self._edit('[{"name": "Principal", "amount": amount - 5}, {"name": "Fee", "amount": 5}]')
        self.assertEqual(
            self._run(self._transaction(amount=Decimal("100"))),
            (Decimal("100"), [("Principal", Decimal("95")), ("Fee", Decimal("5"))]),
        )
        self.rule.transaction_actions.update(value="[]")
        self.assertEqual(self._run(self._transaction(("A", Decimal("3")))), (Decimal("3"), []))

    def test_invalid_parts_leave_the_transaction_alone(self):
        transaction = self._transaction(("A", Decimal("3")))
        for expression in ('"Fee"', '[{"name": "Fee"}]', '[{"name": "", "amount": 1}]',
                           '[{"name": "Refund", "amount": -1}]'):
            with self.subTest(expression=expression):
                self.rule.transaction_actions.all().delete()
                self._edit(expression)
                self.assertEqual(self._run(transaction), (Decimal("3"), [("A", Decimal("3"))]))

    def test_transfers_are_skipped(self):
        out, inc = self._transaction(amount=Decimal("5")), self._transaction(amount=Decimal("5"))
        write_current_user(self.user)
        with patch("apps.rules.signals.check_for_transaction_rules.defer"):
            Transaction.objects.filter(pk=out.pk).update(linked_transaction=inc)
        self._edit('[{"name": "Fee", "amount": 1}]')
        self.assertEqual(self._run(out), (Decimal("5"), []))

    def test_update_or_create_creates_a_transaction_from_its_parts(self):
        UpdateOrCreateTransactionRuleAction.objects.create(
            rule=self.rule, set_account="account_id", set_type="'EX'", set_date="date",
            set_description="'Copy'", set_amount="999",
            set_sub_transactions="sub_transactions + [{'name': 'Fee', 'amount': 1}]",
        )
        self._run(self._transaction(("A", Decimal("3"))))
        copy = Transaction.objects.get(description="Copy")
        self.assertEqual(copy.amount, Decimal("4"))
        self.assertEqual(
            list(copy.sub_transactions.values_list("name", "amount")),
            [("A", Decimal("3")), ("Fee", Decimal("1"))],
        )
