from django.test import TestCase
from django.contrib.auth.models import User
from decimal import Decimal
from datetime import date

from apps.accounts.models import Account, AccountGroup
from apps.currencies.models import Currency
from apps.transactions.models import TransactionCategory, TransactionTag, Transaction, TransactionEntity # Added TransactionEntity just in case, though not used in these specific tests
from apps.rules.models import TransactionRule, TransactionRuleAction, UpdateOrCreateTransactionRuleAction
from apps.rules.tasks import check_for_transaction_rules
from apps.common.middleware.thread_local import set_current_user, delete_current_user
from django.db.models import Q
from unittest.mock import MagicMock


class RulesTasksTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='rulestestuser', email='rules@example.com', password='password')

        set_current_user(self.user)
        self.addCleanup(delete_current_user)

        self.currency = Currency.objects.create(code="RTUSD", name="Rules Test USD", decimal_places=2)
        self.account_group = AccountGroup.objects.create(name="Rules Group", owner=self.user)
        self.account = Account.objects.create(
            name="Rules Account",
            currency=self.currency,
            owner=self.user,
            group=self.account_group
        )
        self.initial_category = TransactionCategory.objects.create(name="Groceries", owner=self.user, type=TransactionCategory.TransactionType.EXPENSE)
        self.new_category = TransactionCategory.objects.create(name="Entertainment", owner=self.user, type=TransactionCategory.TransactionType.EXPENSE)

        self.tag_fun = TransactionTag.objects.create(name="Fun", owner=self.user)
        self.tag_work = TransactionTag.objects.create(name="Work", owner=self.user) # Created but not used in these tests

    def test_rule_changes_category_and_adds_tag_on_create(self):
        rule1 = TransactionRule.objects.create(
            name="Categorize Coffee",
            owner=self.user,
            active=True,
            on_create=True,
            on_update=False,
            trigger="instance.description == 'Coffee Shop'"
        )
        TransactionRuleAction.objects.create(
            rule=rule1,
            field=TransactionRuleAction.Field.CATEGORY,
            value=str(self.new_category.pk) # Use PK for category
        )
        TransactionRuleAction.objects.create(
            rule=rule1,
            field=TransactionRuleAction.Field.TAGS,
            value=f"['{self.tag_fun.name}']" # List of tag names as a string representation of a list
        )

        transaction = Transaction.objects.create(
            account=self.account,
            owner=self.user,
            type=Transaction.Type.EXPENSE,
            date=date(2023,1,1),
            amount=Decimal("5.00"),
            description="Coffee Shop",
            category=self.initial_category
        )

        self.assertEqual(transaction.category, self.initial_category)
        self.assertNotIn(self.tag_fun, transaction.tags.all())

        # Call the task directly, simulating the signal handler
        check_for_transaction_rules(instance_id=transaction.id, user_id=self.user.id, signal_type="transaction_created")

        transaction.refresh_from_db()
        self.assertEqual(transaction.category, self.new_category)
        self.assertIn(self.tag_fun, transaction.tags.all())
        self.assertEqual(transaction.tags.count(), 1)

    def test_rule_trigger_condition_not_met(self):
        rule2 = TransactionRule.objects.create(
            name="Irrelevant Rule",
            owner=self.user,
            active=True,
            on_create=True,
            trigger="instance.description == 'Specific NonMatch'"
        )
        TransactionRuleAction.objects.create(
            rule=rule2,
            field=TransactionRuleAction.Field.CATEGORY,
            value=str(self.new_category.pk)
        )

        transaction = Transaction.objects.create(
            account=self.account,
            owner=self.user,
            type=Transaction.Type.EXPENSE,
            date=date(2023,1,2),
            amount=Decimal("10.00"),
            description="Other item",
            category=self.initial_category
        )

        check_for_transaction_rules(instance_id=transaction.id, user_id=self.user.id, signal_type="transaction_created")

        transaction.refresh_from_db()
        self.assertEqual(transaction.category, self.initial_category)

    def test_rule_on_update_not_on_create(self):
        rule3 = TransactionRule.objects.create(
            name="Update Only Rule",
            owner=self.user,
            active=True,
            on_create=False,
            on_update=True,
            trigger="instance.description == 'Updated Item'"
        )
        TransactionRuleAction.objects.create(
            rule=rule3,
            field=TransactionRuleAction.Field.CATEGORY,
            value=str(self.new_category.pk)
        )

        transaction = Transaction.objects.create(
            account=self.account,
            owner=self.user,
            type=Transaction.Type.EXPENSE,
            date=date(2023,1,3),
            amount=Decimal("15.00"),
            description="Updated Item",
            category=self.initial_category
        )

        # Check on create signal
        check_for_transaction_rules(instance_id=transaction.id, user_id=self.user.id, signal_type="transaction_created")
        transaction.refresh_from_db()
        self.assertEqual(transaction.category, self.initial_category, "Rule should not run on create signal.")

        # Simulate an update by sending the update signal
        check_for_transaction_rules(instance_id=transaction.id, user_id=self.user.id, signal_type="transaction_updated")
        transaction.refresh_from_db()
        self.assertEqual(transaction.category, self.new_category, "Rule should run on update signal.")

    # Example of previous test class that might have been in the file
    # Kept for context if needed, but the new tests are in RulesTasksTests
    # class RulesTestCase(TestCase):
    #     def test_example(self):
    #         self.assertEqual(1 + 1, 2)

    #     def test_rules_index_view_authenticated_user(self):
    #         # ... (implementation from old file) ...
    #         pass

    def test_update_or_create_action_build_search_query(self):
        rule = TransactionRule.objects.create(
            name="Search Rule For Action Test",
            owner=self.user,
            trigger="True" # Simple trigger, not directly used by this action method
        )
        action = UpdateOrCreateTransactionRuleAction.objects.create(
            rule=rule,
            search_description="Coffee",
            search_description_operator=UpdateOrCreateTransactionRuleAction.SearchOperator.CONTAINS,
            search_amount="5", # This will be evaluated by simple_eval
            search_amount_operator=UpdateOrCreateTransactionRuleAction.SearchOperator.EXACT
            # Other search fields can be None or empty
        )

        mock_simple_eval = MagicMock()

        def eval_side_effect(expression_string):
            if expression_string == "Coffee":
                return "Coffee"
            if expression_string == "5": # The value stored in search_amount
                return Decimal("5.00")
            # Add more conditions if other search_ fields are being tested with expressions
            return expression_string # Default pass-through for other potential expressions

        mock_simple_eval.eval = MagicMock(side_effect=eval_side_effect)

        q_object = action.build_search_query(simple_eval=mock_simple_eval)

        self.assertIsInstance(q_object, Q)

        # Convert Q object children to a set of tuples for easier unordered comparison
        # Q objects can be nested. For this specific case, we expect a flat AND structure.
        # (AND: ('description__contains', 'Coffee'), ('amount__exact', Decimal('5.00')))

        children_set = set(q_object.children)

        expected_children = {
            ('description__contains', 'Coffee'),
            ('amount__exact', Decimal('5.00'))
        }

        self.assertEqual(q_object.connector, Q.AND)
        self.assertEqual(children_set, expected_children)

        # Verify that simple_eval.eval was called for 'Coffee' and '5'
        # Check calls to the mock_simple_eval.eval mock specifically
        mock_simple_eval.eval.assert_any_call("Coffee")
        mock_simple_eval.eval.assert_any_call("5")
