import datetime
from decimal import Decimal
from datetime import date, timedelta

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal
import datetime # Import was missing

from apps.transactions.models import (
    TransactionCategory,
    TransactionTag,
    TransactionEntity, # Added
    Transaction,
    InstallmentPlan,
    RecurringTransaction,
)
from apps.accounts.models import Account, AccountGroup
from apps.currencies.models import Currency, ExchangeRate

User = get_user_model()


class BaseTransactionAppTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="testuser@example.com", password="password")
        self.other_user = User.objects.create_user(email="otheruser@example.com", password="password")
        self.client = Client()
        self.client.login(email="testuser@example.com", password="password")

        self.currency = Currency.objects.create(
            code="USD", name="US Dollar", decimal_places=2, prefix="$ "
        )
        self.account_group = AccountGroup.objects.create(name="Test Group", owner=self.user)
        self.account = Account.objects.create(
            name="Test Account", group=self.account_group, currency=self.currency, owner=self.user
        )


class TransactionCategoryTests(BaseTransactionAppTest):
    def test_category_creation(self):
        """Test basic category creation by a user."""
        category = TransactionCategory.objects.create(name="Groceries", owner=self.user)
        self.assertEqual(str(category), "Groceries")
        self.assertFalse(category.mute)
        self.assertTrue(category.active)
        self.assertEqual(category.owner, self.user)

    def test_category_creation_view(self):
        response = self.client.post(reverse("category_add"), {"name": "Utilities", "active": "on"})
        self.assertEqual(response.status_code, 204) # HTMX success, no content
        self.assertTrue(TransactionCategory.objects.filter(name="Utilities", owner=self.user).exists())

    def test_category_edit_view(self):
        category = TransactionCategory.objects.create(name="Initial Name", owner=self.user)
        response = self.client.post(reverse("category_edit", args=[category.id]), {"name": "Updated Name", "mute": "on", "active": "on"})
        self.assertEqual(response.status_code, 204)
        category.refresh_from_db()
        self.assertEqual(category.name, "Updated Name")
        self.assertTrue(category.mute)

    def test_category_delete_view(self):
        category = TransactionCategory.objects.create(name="To Delete", owner=self.user)
        response = self.client.delete(reverse("category_delete", args=[category.id]))
        self.assertEqual(response.status_code, 204)
        self.assertFalse(TransactionCategory.all_objects.filter(id=category.id).exists()) # all_objects to check even if soft deleted by mistake

    def test_other_user_cannot_edit_category(self):
        category = TransactionCategory.objects.create(name="User1s Category", owner=self.user)
        self.client.logout()
        self.client.login(email="otheruser@example.com", password="password")
        response = self.client.post(reverse("category_edit", args=[category.id]), {"name": "Attempted Update"})
        # This should return a 204 with a message, not a 403, as per view logic for owned objects
        self.assertEqual(response.status_code, 204)
        category.refresh_from_db()
        self.assertEqual(category.name, "User1s Category") # Name should not change

    def test_category_sharing_and_visibility(self):
        category = TransactionCategory.objects.create(name="Shared Cat", owner=self.user, visibility=TransactionCategory.Visibility.SHARED)
        category.shared_with.add(self.other_user)

        # Other user should be able to see it (though not directly tested here, view logic would permit)
        # Test that owner can still edit
        response = self.client.post(reverse("category_edit", args=[category.id]), {"name": "Owner Edited Shared Cat", "active":"on"})
        self.assertEqual(response.status_code, 204)
        category.refresh_from_db()
        self.assertEqual(category.name, "Owner Edited Shared Cat")

        # Test other user cannot delete if not owner
        self.client.logout()
        self.client.login(email="otheruser@example.com", password="password")
        response = self.client.delete(reverse("category_delete", args=[category.id])) # This removes user from shared_with
        self.assertEqual(response.status_code, 204)
        category.refresh_from_db()
        self.assertTrue(TransactionCategory.all_objects.filter(id=category.id).exists())
        self.assertNotIn(self.other_user, category.shared_with.all())


class TransactionTagTests(BaseTransactionAppTest):
    def test_tag_creation(self):
        """Test basic tag creation by a user."""
        tag = TransactionTag.objects.create(name="Essential", owner=self.user)
        self.assertEqual(str(tag), "Essential")
        self.assertTrue(tag.active)
        self.assertEqual(tag.owner, self.user)

    def test_tag_creation_view(self):
        response = self.client.post(reverse("tag_add"), {"name": "Vacation", "active": "on"})
        self.assertEqual(response.status_code, 204)
        self.assertTrue(TransactionTag.objects.filter(name="Vacation", owner=self.user).exists())

    def test_tag_edit_view(self):
        tag = TransactionTag.objects.create(name="Old Tag", owner=self.user)
        response = self.client.post(reverse("tag_edit", args=[tag.id]), {"name": "New Tag", "active": "on"})
        self.assertEqual(response.status_code, 204)
        tag.refresh_from_db()
        self.assertEqual(tag.name, "New Tag")

    def test_tag_delete_view(self):
        tag = TransactionTag.objects.create(name="Delete Me Tag", owner=self.user)
        response = self.client.delete(reverse("tag_delete", args=[tag.id]))
        self.assertEqual(response.status_code, 204)
        self.assertFalse(TransactionTag.all_objects.filter(id=tag.id).exists())


class TransactionEntityTests(BaseTransactionAppTest):
    def test_entity_creation(self):
        """Test basic entity creation by a user."""
        entity = TransactionEntity.objects.create(name="Supermarket X", owner=self.user)
        self.assertEqual(str(entity), "Supermarket X")
        self.assertTrue(entity.active)
        self.assertEqual(entity.owner, self.user)

    def test_entity_creation_view(self):
        response = self.client.post(reverse("entity_add"), {"name": "Online Store", "active": "on"})
        self.assertEqual(response.status_code, 204)
        self.assertTrue(TransactionEntity.objects.filter(name="Online Store", owner=self.user).exists())

    def test_entity_edit_view(self):
        entity = TransactionEntity.objects.create(name="Local Shop", owner=self.user)
        response = self.client.post(reverse("entity_edit", args=[entity.id]), {"name": "Local Shop Inc.", "active": "on"})
        self.assertEqual(response.status_code, 204)
        entity.refresh_from_db()
        self.assertEqual(entity.name, "Local Shop Inc.")

    def test_entity_delete_view(self):
        entity = TransactionEntity.objects.create(name="To Be Removed Entity", owner=self.user)
        response = self.client.delete(reverse("entity_delete", args=[entity.id]))
        self.assertEqual(response.status_code, 204)
        self.assertFalse(TransactionEntity.all_objects.filter(id=entity.id).exists())


class TransactionTests(BaseTransactionAppTest): # Inherit from BaseTransactionAppTest
    def setUp(self):
        super().setUp() # Call BaseTransactionAppTest's setUp
        """Set up test data"""
        # self.category is already created in BaseTransactionAppTest if needed,
        # or create specific ones here.
        self.category = TransactionCategory.objects.create(name="Test Category", owner=self.user)
        self.tag = TransactionTag.objects.create(name="Test Tag", owner=self.user)
        self.entity = TransactionEntity.objects.create(name="Test Entity", owner=self.user)

    def test_transaction_creation(self):
        """Test basic transaction creation with required fields"""
        transaction = Transaction.objects.create(
            account=self.account,
            owner=self.user, # Assign owner
            type=Transaction.Type.EXPENSE,
            date=timezone.now().date(),
            amount=Decimal("100.00"),
            description="Test transaction",
            category=self.category,
        )
        transaction.tags.add(self.tag)
        transaction.entities.add(self.entity)

        self.assertTrue(transaction.is_paid)
        self.assertEqual(transaction.type, Transaction.Type.EXPENSE)
        self.assertEqual(transaction.account.currency.code, "USD")
        self.assertEqual(transaction.owner, self.user)
        self.assertIn(self.tag, transaction.tags.all())
        self.assertIn(self.entity, transaction.entities.all())


    def test_transaction_creation_view(self):
        data = {
            "account": self.account.id,
            "type": Transaction.Type.INCOME,
            "is_paid": "on",
            "date": timezone.now().date().isoformat(),
            "amount": "250.75",
            "description": "Freelance Gig",
            "category": self.category.id,
            "tags": [self.tag.name], # Dynamic fields expect names for creation/selection
            "entities": [self.entity.name]
        }
        response = self.client.post(reverse("transaction_add"), data)
        self.assertEqual(response.status_code, 204, response.content.decode() if response.content else "No content")
        self.assertTrue(
            Transaction.objects.filter(description="Freelance Gig", owner=self.user, amount=Decimal("250.75")).exists()
        )
        # Check that tag and entity were associated (or created if DynamicModel...Field handled it)
        created_transaction = Transaction.objects.get(description="Freelance Gig")
        self.assertIn(self.tag, created_transaction.tags.all())
        self.assertIn(self.entity, created_transaction.entities.all())


    def test_transaction_edit_view(self):
        transaction = Transaction.objects.create(
            account=self.account, owner=self.user, type=Transaction.Type.EXPENSE,
            date=timezone.now().date(), amount=Decimal("50.00"), description="Initial"
        )
        updated_description = "Updated Description"
        updated_amount = "75.25"
        response = self.client.post(
            reverse("transaction_edit", args=[transaction.id]),
            {
                "account": self.account.id, "type": Transaction.Type.EXPENSE, "is_paid": "on",
                "date": transaction.date.isoformat(), "amount": updated_amount,
                "description": updated_description, "category": self.category.id
            }
        )
        self.assertEqual(response.status_code, 204)
        transaction.refresh_from_db()
        self.assertEqual(transaction.description, updated_description)
        self.assertEqual(transaction.amount, Decimal(updated_amount))


    def test_transaction_soft_delete_view(self):
        transaction = Transaction.objects.create(
            account=self.account, owner=self.user, type=Transaction.Type.EXPENSE,
            date=timezone.now().date(), amount=Decimal("10.00"), description="To Soft Delete"
        )
        response = self.client.delete(reverse("transaction_delete", args=[transaction.id]))
        self.assertEqual(response.status_code, 204)
        transaction.refresh_from_db()
        self.assertTrue(transaction.deleted)
        self.assertIsNotNone(transaction.deleted_at)
        self.assertTrue(Transaction.deleted_objects.filter(id=transaction.id).exists())
        self.assertFalse(Transaction.objects.filter(id=transaction.id).exists()) # Default manager should not find it

    def test_transaction_hard_delete_after_soft_delete(self):
        # First soft delete
        transaction = Transaction.objects.create(
            account=self.account, owner=self.user, type=Transaction.Type.EXPENSE,
            date=timezone.now().date(), amount=Decimal("15.00"), description="To Hard Delete"
        )
        transaction.delete() # Soft delete via model method
        self.assertTrue(Transaction.deleted_objects.filter(id=transaction.id).exists())

        # Then hard delete via view (which calls model's delete again on an already soft-deleted item)
        response = self.client.delete(reverse("transaction_delete", args=[transaction.id]))
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Transaction.all_objects.filter(id=transaction.id).exists())


    def test_transaction_undelete_view(self):
        transaction = Transaction.objects.create(
            account=self.account, owner=self.user, type=Transaction.Type.EXPENSE,
            date=timezone.now().date(), amount=Decimal("20.00"), description="To Undelete"
        )
        transaction.delete() # Soft delete
        transaction.refresh_from_db()
        self.assertTrue(transaction.deleted)

        response = self.client.get(reverse("transaction_undelete", args=[transaction.id]))
        self.assertEqual(response.status_code, 204)
        transaction.refresh_from_db()
        self.assertFalse(transaction.deleted)
        self.assertIsNone(transaction.deleted_at)
        self.assertTrue(Transaction.objects.filter(id=transaction.id).exists())


    def test_transaction_with_exchange_currency(self):
        """Test transaction with exchange currency"""
        eur = Currency.objects.create(
            code="EUR", name="Euro", decimal_places=2, prefix="€", owner=self.user
        )
        self.account.exchange_currency = eur
        self.account.save()

        # Create exchange rate
        ExchangeRate.objects.create(
            from_currency=self.currency,
            to_currency=eur,
            rate=Decimal("0.85"),
            date=timezone.now().date(), # Ensure date matches transaction or is general
            owner=self.user
        )

        transaction = Transaction.objects.create(
            account=self.account,
            owner=self.user,
            type=Transaction.Type.EXPENSE,
            date=timezone.now().date(),
            amount=Decimal("100.00"),
            description="Test transaction",
        )

        exchanged = transaction.exchanged_amount()
        self.assertIsNotNone(exchanged)
        self.assertEqual(exchanged["prefix"], "€")
        # Depending on exact conversion logic, you might want to check the amount too
        # self.assertEqual(exchanged["amount"], Decimal("85.00"))

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
            owner=self.user,
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
            owner=self.user,
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

    def test_transaction_transfer_view(self):
        other_account = Account.objects.create(
            name="Other Account", group=self.account_group, currency=self.currency, owner=self.user
        )
        data = {
            "from_account": self.account.id,
            "to_account": other_account.id,
            "from_amount": "100.00",
            "to_amount": "100.00", # Assuming same currency for simplicity
            "date": timezone.now().date().isoformat(),
            "description": "Test Transfer",
        }
        response = self.client.post(reverse("transactions_transfer"), data)
        self.assertEqual(response.status_code, 204)
        self.assertTrue(
            Transaction.objects.filter(account=self.account, type=Transaction.Type.EXPENSE, amount="100.00").exists()
        )
        self.assertTrue(
            Transaction.objects.filter(account=other_account, type=Transaction.Type.INCOME, amount="100.00").exists()
        )

    def test_transaction_bulk_edit_view(self):
        t1 = Transaction.objects.create(
            account=self.account, owner=self.user, type=Transaction.Type.EXPENSE,
            date=timezone.now().date(), amount=Decimal("10.00"), description="Bulk 1"
        )
        t2 = Transaction.objects.create(
            account=self.account, owner=self.user, type=Transaction.Type.EXPENSE,
            date=timezone.now().date(), amount=Decimal("20.00"), description="Bulk 2"
        )
        new_category = TransactionCategory.objects.create(name="Bulk Category", owner=self.user)
        data = {
            "transactions": [t1.id, t2.id],
            "category": new_category.id,
            "is_paid": "true", # NullBoolean can be 'true', 'false', or empty for no change
        }
        response = self.client.post(reverse("transactions_bulk_edit"), data)
        self.assertEqual(response.status_code, 204)
        t1.refresh_from_db()
        t2.refresh_from_db()
        self.assertEqual(t1.category, new_category)
        self.assertEqual(t2.category, new_category)
        self.assertTrue(t1.is_paid)
        self.assertTrue(t2.is_paid)


class InstallmentPlanTests(BaseTransactionAppTest): # Inherit from BaseTransactionAppTest
    def setUp(self):
        super().setUp() # Call BaseTransactionAppTest's setUp
        # self.currency and self.account are available from base
        self.category = TransactionCategory.objects.create(name="Installments", owner=self.user)

    def test_installment_plan_creation_and_transaction_generation(self):
        """Test basic installment plan creation and its transaction generation."""
        start_date = timezone.now().date()
        plan = InstallmentPlan.objects.create(
            account=self.account,
            owner=self.user,
            type=Transaction.Type.EXPENSE,
            description="Test Plan",
            number_of_installments=3,
            start_date=start_date,
            installment_amount=Decimal("100.00"),
            recurrence=InstallmentPlan.Recurrence.MONTHLY,
            category=self.category,
        )
        plan.create_transactions() # Manually call as it's not in save in the form

        self.assertEqual(plan.transactions.count(), 3)
        first_transaction = plan.transactions.order_by('date').first()
        self.assertEqual(first_transaction.amount, Decimal("100.00"))
        self.assertEqual(first_transaction.date, start_date)
        self.assertEqual(first_transaction.category, self.category)

    def test_installment_plan_update_transactions(self):
        start_date = timezone.now().date()
        plan = InstallmentPlan.objects.create(
            account=self.account, owner=self.user, type=Transaction.Type.EXPENSE,
            description="Initial Plan", number_of_installments=2, start_date=start_date,
            installment_amount=Decimal("50.00"), recurrence=InstallmentPlan.Recurrence.MONTHLY,
        )
        plan.create_transactions()
        self.assertEqual(plan.transactions.count(), 2)

        plan.description = "Updated Plan Description"
        plan.installment_amount = Decimal("60.00")
        plan.number_of_installments = 3 # Increase installments
        plan.save() # This should trigger _calculate_end_date and _calculate_installment_total_number
        plan.update_transactions() # Manually call as it's not in save in the form

        self.assertEqual(plan.transactions.count(), 3)
        updated_transaction = plan.transactions.order_by('date').first()
        self.assertEqual(updated_transaction.description, "Updated Plan Description")
        # Amount should not change if already paid, but these are created as unpaid
        self.assertEqual(updated_transaction.amount, Decimal("60.00"))


    def test_installment_plan_delete_with_transactions(self):
        plan = InstallmentPlan.objects.create(
            account=self.account, owner=self.user, type=Transaction.Type.EXPENSE,
            description="Plan to Delete", number_of_installments=2, start_date=timezone.now().date(),
            installment_amount=Decimal("25.00"), recurrence=InstallmentPlan.Recurrence.MONTHLY,
        )
        plan.create_transactions()
        plan_id = plan.id
        self.assertTrue(Transaction.objects.filter(installment_plan_id=plan_id).exists())

        plan.delete() # This should also delete related transactions as per model's delete
        self.assertFalse(InstallmentPlan.all_objects.filter(id=plan_id).exists())
        self.assertFalse(Transaction.all_objects.filter(installment_plan_id=plan_id).exists())


class RecurringTransactionTests(BaseTransactionAppTest): # Inherit
    def setUp(self):
        super().setUp()
        self.category = TransactionCategory.objects.create(name="Recurring Category", owner=self.user)

    def test_recurring_transaction_creation_and_upcoming_generation(self):
        """Test basic recurring transaction creation and initial upcoming transaction generation."""
        start_date = timezone.now().date()
        recurring = RecurringTransaction.objects.create(
            account=self.account,
            owner=self.user,
            type=Transaction.Type.INCOME,
            amount=Decimal("200.00"),
            description="Monthly Salary",
            start_date=start_date,
            recurrence_type=RecurringTransaction.RecurrenceType.MONTH,
            recurrence_interval=1,
            category=self.category,
        )
        recurring.create_upcoming_transactions() # Manually call

        # It should create a few transactions (e.g., for next 5 occurrences or up to end_date)
        self.assertTrue(recurring.transactions.count() > 0)
        first_upcoming = recurring.transactions.order_by('date').first()
        self.assertEqual(first_upcoming.amount, Decimal("200.00"))
        self.assertEqual(first_upcoming.date, start_date) # First one should be on start_date
        self.assertFalse(first_upcoming.is_paid)

    def test_recurring_transaction_update_unpaid(self):
        recurring = RecurringTransaction.objects.create(
            account=self.account, owner=self.user, type=Transaction.Type.EXPENSE,
            amount=Decimal("30.00"), description="Subscription", start_date=timezone.now().date(),
            recurrence_type=RecurringTransaction.RecurrenceType.MONTH, recurrence_interval=1
        )
        recurring.create_upcoming_transactions()
        unpaid_transaction = recurring.transactions.filter(is_paid=False).first()
        self.assertIsNotNone(unpaid_transaction)

        recurring.amount = Decimal("35.00")
        recurring.description = "Updated Subscription"
        recurring.save()
        recurring.update_unpaid_transactions() # Manually call

        unpaid_transaction.refresh_from_db()
        self.assertEqual(unpaid_transaction.amount, Decimal("35.00"))
        self.assertEqual(unpaid_transaction.description, "Updated Subscription")

    def test_recurring_transaction_delete_unpaid(self):
        recurring = RecurringTransaction.objects.create(
            account=self.account, owner=self.user, type=Transaction.Type.EXPENSE,
            amount=Decimal("40.00"), description="Service Fee", start_date=timezone.now().date() + timedelta(days=5), # future start
            recurrence_type=RecurringTransaction.RecurrenceType.MONTH, recurrence_interval=1
        )
        recurring.create_upcoming_transactions()
        self.assertTrue(recurring.transactions.filter(is_paid=False).exists())

        recurring.delete_unpaid_transactions() # Manually call
        # This method in the model deletes transactions with date > today
        self.assertFalse(recurring.transactions.filter(is_paid=False, date__gt=timezone.now().date()).exists())
