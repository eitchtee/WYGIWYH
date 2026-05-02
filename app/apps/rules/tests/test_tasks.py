from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase

from apps.accounts.models import Account
from apps.currencies.models import Currency
from apps.rules.models import TransactionRule, UpdateOrCreateTransactionRuleAction
from apps.rules.tasks import check_for_transaction_rules
from apps.transactions.models import Transaction


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
