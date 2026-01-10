from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account, AccountGroup
from apps.currencies.models import Currency
from apps.dca.models import DCAStrategy, DCAEntry
from apps.transactions.models import (
    Transaction,
    TransactionCategory,
    TransactionTag,
    TransactionEntity,
    InstallmentPlan,
    RecurringTransaction,
)


ACCESS_DENIED_CODES = [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND]


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
    WHITENOISE_AUTOREFRESH=True,
)
class AccountDataIsolationTests(TestCase):
    """Tests to ensure users cannot access other users' accounts."""

    def setUp(self):
        """Set up test data with two distinct users."""
        User = get_user_model()

        # User 1 - the requester
        self.user1 = User.objects.create_user(
            email="user1@test.com", password="testpass123"
        )
        self.client1 = APIClient()
        self.client1.force_authenticate(user=self.user1)

        # User 2 - owner of data that user1 should NOT access
        self.user2 = User.objects.create_user(
            email="user2@test.com", password="testpass123"
        )
        self.client2 = APIClient()
        self.client2.force_authenticate(user=self.user2)

        # Shared currency
        self.currency = Currency.objects.create(
            code="USD", name="US Dollar", decimal_places=2, prefix="$ "
        )

        # User 1's account
        self.user1_account_group = AccountGroup.all_objects.create(
            name="User1 Group", owner=self.user1
        )
        self.user1_account = Account.all_objects.create(
            name="User1 Account",
            group=self.user1_account_group,
            currency=self.currency,
            owner=self.user1,
        )

        # User 2's account (private, should be invisible to user1)
        self.user2_account_group = AccountGroup.all_objects.create(
            name="User2 Group", owner=self.user2
        )
        self.user2_account = Account.all_objects.create(
            name="User2 Account",
            group=self.user2_account_group,
            currency=self.currency,
            owner=self.user2,
        )

    def test_user_cannot_see_other_users_accounts_in_list(self):
        """GET /api/accounts/ should only return user's own accounts."""
        response = self.client1.get("/api/accounts/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # User1 should only see their own account
        account_ids = [acc["id"] for acc in response.data["results"]]
        self.assertIn(self.user1_account.id, account_ids)
        self.assertNotIn(self.user2_account.id, account_ids)

    def test_user_cannot_access_other_users_account_detail(self):
        """GET /api/accounts/{id}/ should deny access to other user's account."""
        response = self.client1.get(f"/api/accounts/{self.user2_account.id}/")

        self.assertIn(response.status_code, ACCESS_DENIED_CODES)

    def test_user_cannot_modify_other_users_account(self):
        """PATCH on other user's account should deny access."""
        response = self.client1.patch(
            f"/api/accounts/{self.user2_account.id}/",
            {"name": "Hacked Account"},
        )
        self.assertIn(response.status_code, ACCESS_DENIED_CODES)

        # Verify account name wasn't changed
        self.user2_account.refresh_from_db()
        self.assertEqual(self.user2_account.name, "User2 Account")

    def test_user_cannot_delete_other_users_account(self):
        """DELETE on other user's account should deny access."""
        response = self.client1.delete(f"/api/accounts/{self.user2_account.id}/")

        self.assertIn(response.status_code, ACCESS_DENIED_CODES)

        # Verify account still exists
        self.assertTrue(Account.all_objects.filter(id=self.user2_account.id).exists())

    def test_user_cannot_get_balance_of_other_users_account(self):
        """Balance action on other user's account should deny access."""
        response = self.client1.get(f"/api/accounts/{self.user2_account.id}/balance/")

        self.assertIn(response.status_code, ACCESS_DENIED_CODES)

    def test_user_can_access_own_account(self):
        """User can access their own account normally."""
        response = self.client1.get(f"/api/accounts/{self.user1_account.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "User1 Account")


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
    WHITENOISE_AUTOREFRESH=True,
)
class AccountGroupDataIsolationTests(TestCase):
    """Tests to ensure users cannot access other users' account groups."""

    def setUp(self):
        """Set up test data with two distinct users."""
        User = get_user_model()

        self.user1 = User.objects.create_user(
            email="user1@test.com", password="testpass123"
        )
        self.client1 = APIClient()
        self.client1.force_authenticate(user=self.user1)

        self.user2 = User.objects.create_user(
            email="user2@test.com", password="testpass123"
        )

        # User 1's account group
        self.user1_group = AccountGroup.all_objects.create(
            name="User1 Group", owner=self.user1
        )

        # User 2's account group
        self.user2_group = AccountGroup.all_objects.create(
            name="User2 Group", owner=self.user2
        )

    def test_user_cannot_see_other_users_account_groups(self):
        """GET /api/account-groups/ should only return user's own groups."""
        response = self.client1.get("/api/account-groups/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        group_ids = [grp["id"] for grp in response.data["results"]]
        self.assertIn(self.user1_group.id, group_ids)
        self.assertNotIn(self.user2_group.id, group_ids)

    def test_user_cannot_access_other_users_account_group_detail(self):
        """GET /api/account-groups/{id}/ should deny access to other user's group."""
        response = self.client1.get(f"/api/account-groups/{self.user2_group.id}/")

        self.assertIn(response.status_code, ACCESS_DENIED_CODES)

    def test_user_cannot_modify_other_users_account_group(self):
        """PATCH on other user's account group should deny access."""
        response = self.client1.patch(
            f"/api/account-groups/{self.user2_group.id}/",
            {"name": "Hacked Group"},
        )

        self.assertIn(response.status_code, ACCESS_DENIED_CODES)

        self.user2_group.refresh_from_db()
        self.assertEqual(self.user2_group.name, "User2 Group")

    def test_user_cannot_delete_other_users_account_group(self):
        """DELETE on other user's account group should deny access."""
        response = self.client1.delete(f"/api/account-groups/{self.user2_group.id}/")

        self.assertIn(response.status_code, ACCESS_DENIED_CODES)

        self.assertTrue(
            AccountGroup.all_objects.filter(id=self.user2_group.id).exists()
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
class TransactionDataIsolationTests(TestCase):
    """Tests to ensure users cannot access other users' transactions."""

    def setUp(self):
        """Set up test data with transactions for two distinct users."""
        User = get_user_model()

        self.user1 = User.objects.create_user(
            email="user1@test.com", password="testpass123"
        )
        self.client1 = APIClient()
        self.client1.force_authenticate(user=self.user1)

        self.user2 = User.objects.create_user(
            email="user2@test.com", password="testpass123"
        )

        self.currency = Currency.objects.create(
            code="USD", name="US Dollar", decimal_places=2, prefix="$ "
        )

        # User 1's account and transaction
        self.user1_account = Account.all_objects.create(
            name="User1 Account", currency=self.currency, owner=self.user1
        )
        self.user1_transaction = Transaction.userless_all_objects.create(
            account=self.user1_account,
            type=Transaction.Type.INCOME,
            amount=Decimal("100.00"),
            is_paid=True,
            date=date(2025, 1, 1),
            description="User1 Income",
            owner=self.user1,
        )

        # User 2's account and transaction
        self.user2_account = Account.all_objects.create(
            name="User2 Account", currency=self.currency, owner=self.user2
        )
        self.user2_transaction = Transaction.userless_all_objects.create(
            account=self.user2_account,
            type=Transaction.Type.EXPENSE,
            amount=Decimal("50.00"),
            is_paid=True,
            date=date(2025, 1, 1),
            description="User2 Expense",
            owner=self.user2,
        )

    def test_user_cannot_see_other_users_transactions_in_list(self):
        """GET /api/transactions/ should only return user's own transactions."""
        response = self.client1.get("/api/transactions/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        transaction_ids = [t["id"] for t in response.data["results"]]
        self.assertIn(self.user1_transaction.id, transaction_ids)
        self.assertNotIn(self.user2_transaction.id, transaction_ids)

    def test_user_cannot_access_other_users_transaction_detail(self):
        """GET /api/transactions/{id}/ should deny access to other user's transaction."""
        response = self.client1.get(f"/api/transactions/{self.user2_transaction.id}/")

        self.assertIn(response.status_code, ACCESS_DENIED_CODES)

    def test_user_cannot_modify_other_users_transaction(self):
        """PATCH on other user's transaction should deny access."""
        response = self.client1.patch(
            f"/api/transactions/{self.user2_transaction.id}/",
            {"description": "Hacked Transaction"},
        )

        self.assertIn(response.status_code, ACCESS_DENIED_CODES)

        self.user2_transaction.refresh_from_db()
        self.assertEqual(self.user2_transaction.description, "User2 Expense")

    def test_user_cannot_delete_other_users_transaction(self):
        """DELETE on other user's transaction should deny access."""
        response = self.client1.delete(
            f"/api/transactions/{self.user2_transaction.id}/"
        )

        self.assertIn(response.status_code, ACCESS_DENIED_CODES)

        self.assertTrue(
            Transaction.userless_all_objects.filter(
                id=self.user2_transaction.id
            ).exists()
        )

    def test_user_cannot_create_transaction_in_other_users_account(self):
        """POST /api/transactions/ with other user's account should fail."""
        response = self.client1.post(
            "/api/transactions/",
            {
                "account": self.user2_account.id,
                "type": "IN",
                "amount": "100.00",
                "date": "2025-01-15",
                "description": "Sneaky transaction",
            },
            format="json",
        )

        # Should deny access - 400 (validation error), 403, or 404
        self.assertIn(
            response.status_code,
            ACCESS_DENIED_CODES + [status.HTTP_400_BAD_REQUEST],
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
class CategoryTagEntityIsolationTests(TestCase):
    """Tests for isolation of categories, tags, and entities between users."""

    def setUp(self):
        """Set up test data."""
        User = get_user_model()

        self.user1 = User.objects.create_user(
            email="user1@test.com", password="testpass123"
        )
        self.client1 = APIClient()
        self.client1.force_authenticate(user=self.user1)

        self.user2 = User.objects.create_user(
            email="user2@test.com", password="testpass123"
        )

        # User 1's categories, tags, entities
        self.user1_category = TransactionCategory.all_objects.create(
            name="User1 Category", owner=self.user1
        )
        self.user1_tag = TransactionTag.all_objects.create(
            name="User1 Tag", owner=self.user1
        )
        self.user1_entity = TransactionEntity.all_objects.create(
            name="User1 Entity", owner=self.user1
        )

        # User 2's categories, tags, entities
        self.user2_category = TransactionCategory.all_objects.create(
            name="User2 Category", owner=self.user2
        )
        self.user2_tag = TransactionTag.all_objects.create(
            name="User2 Tag", owner=self.user2
        )
        self.user2_entity = TransactionEntity.all_objects.create(
            name="User2 Entity", owner=self.user2
        )

    def test_user_cannot_see_other_users_categories(self):
        """GET /api/categories/ should only return user's own categories."""
        response = self.client1.get("/api/categories/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        category_ids = [c["id"] for c in response.data["results"]]
        self.assertIn(self.user1_category.id, category_ids)
        self.assertNotIn(self.user2_category.id, category_ids)

    def test_user_cannot_access_other_users_category_detail(self):
        """GET /api/categories/{id}/ should deny access to other user's category."""
        response = self.client1.get(f"/api/categories/{self.user2_category.id}/")

        self.assertIn(response.status_code, ACCESS_DENIED_CODES)

    def test_user_cannot_see_other_users_tags(self):
        """GET /api/tags/ should only return user's own tags."""
        response = self.client1.get("/api/tags/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        tag_ids = [t["id"] for t in response.data["results"]]
        self.assertIn(self.user1_tag.id, tag_ids)
        self.assertNotIn(self.user2_tag.id, tag_ids)

    def test_user_cannot_access_other_users_tag_detail(self):
        """GET /api/tags/{id}/ should deny access to other user's tag."""
        response = self.client1.get(f"/api/tags/{self.user2_tag.id}/")

        self.assertIn(response.status_code, ACCESS_DENIED_CODES)

    def test_user_cannot_see_other_users_entities(self):
        """GET /api/entities/ should only return user's own entities."""
        response = self.client1.get("/api/entities/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        entity_ids = [e["id"] for e in response.data["results"]]
        self.assertIn(self.user1_entity.id, entity_ids)
        self.assertNotIn(self.user2_entity.id, entity_ids)

    def test_user_cannot_access_other_users_entity_detail(self):
        """GET /api/entities/{id}/ should deny access to other user's entity."""
        response = self.client1.get(f"/api/entities/{self.user2_entity.id}/")

        self.assertIn(response.status_code, ACCESS_DENIED_CODES)

    def test_user_cannot_modify_other_users_category(self):
        """PATCH on other user's category should deny access."""
        response = self.client1.patch(
            f"/api/categories/{self.user2_category.id}/",
            {"name": "Hacked Category"},
        )

        self.assertIn(response.status_code, ACCESS_DENIED_CODES)

    def test_user_cannot_delete_other_users_tag(self):
        """DELETE on other user's tag should deny access."""
        response = self.client1.delete(f"/api/tags/{self.user2_tag.id}/")

        self.assertIn(response.status_code, ACCESS_DENIED_CODES)

        self.assertTrue(
            TransactionTag.all_objects.filter(id=self.user2_tag.id).exists()
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
class DCADataIsolationTests(TestCase):
    """Tests to ensure users cannot access other users' DCA strategies and entries."""

    def setUp(self):
        """Set up test data."""
        User = get_user_model()

        self.user1 = User.objects.create_user(
            email="user1@test.com", password="testpass123"
        )
        self.client1 = APIClient()
        self.client1.force_authenticate(user=self.user1)

        self.user2 = User.objects.create_user(
            email="user2@test.com", password="testpass123"
        )

        self.currency1 = Currency.objects.create(
            code="BTC", name="Bitcoin", decimal_places=8, prefix=""
        )
        self.currency2 = Currency.objects.create(
            code="USD", name="US Dollar", decimal_places=2, prefix="$ "
        )

        # User 1's DCA strategy and entry
        self.user1_strategy = DCAStrategy.all_objects.create(
            name="User1 BTC Strategy",
            target_currency=self.currency1,
            payment_currency=self.currency2,
            owner=self.user1,
        )
        self.user1_entry = DCAEntry.objects.create(
            strategy=self.user1_strategy,
            date=date(2025, 1, 1),
            amount_paid=Decimal("100.00"),
            amount_received=Decimal("0.001"),
        )

        # User 2's DCA strategy and entry
        self.user2_strategy = DCAStrategy.all_objects.create(
            name="User2 BTC Strategy",
            target_currency=self.currency1,
            payment_currency=self.currency2,
            owner=self.user2,
        )
        self.user2_entry = DCAEntry.objects.create(
            strategy=self.user2_strategy,
            date=date(2025, 1, 1),
            amount_paid=Decimal("200.00"),
            amount_received=Decimal("0.002"),
        )

    def test_user_cannot_see_other_users_dca_strategies(self):
        """GET /api/dca/strategies/ should only return user's own strategies."""
        response = self.client1.get("/api/dca/strategies/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        strategy_ids = [s["id"] for s in response.data["results"]]
        self.assertIn(self.user1_strategy.id, strategy_ids)
        self.assertNotIn(self.user2_strategy.id, strategy_ids)

    def test_user_cannot_access_other_users_dca_strategy_detail(self):
        """GET /api/dca/strategies/{id}/ should deny access to other user's strategy."""
        response = self.client1.get(f"/api/dca/strategies/{self.user2_strategy.id}/")

        self.assertIn(response.status_code, ACCESS_DENIED_CODES)

    def test_user_cannot_access_other_users_dca_entries(self):
        """GET /api/dca/entries/ filtered by other user's strategy should return empty."""
        response = self.client1.get(
            f"/api/dca/entries/?strategy={self.user2_strategy.id}"
        )

        # Either OK with empty results or error
        if response.status_code == status.HTTP_200_OK:
            entry_ids = [e["id"] for e in response.data["results"]]
            self.assertNotIn(self.user2_entry.id, entry_ids)

    def test_user_cannot_access_other_users_dca_entry_detail(self):
        """GET /api/dca/entries/{id}/ should deny access to other user's entry."""
        response = self.client1.get(f"/api/dca/entries/{self.user2_entry.id}/")

        self.assertIn(response.status_code, ACCESS_DENIED_CODES)

    def test_user_cannot_access_other_users_strategy_investment_frequency(self):
        """investment_frequency action on other user's strategy should deny access."""
        response = self.client1.get(
            f"/api/dca/strategies/{self.user2_strategy.id}/investment_frequency/"
        )

        self.assertIn(response.status_code, ACCESS_DENIED_CODES)

    def test_user_cannot_access_other_users_strategy_price_comparison(self):
        """price_comparison action on other user's strategy should deny access."""
        response = self.client1.get(
            f"/api/dca/strategies/{self.user2_strategy.id}/price_comparison/"
        )

        self.assertIn(response.status_code, ACCESS_DENIED_CODES)

    def test_user_cannot_access_other_users_strategy_current_price(self):
        """current_price action on other user's strategy should deny access."""
        response = self.client1.get(
            f"/api/dca/strategies/{self.user2_strategy.id}/current_price/"
        )

        self.assertIn(response.status_code, ACCESS_DENIED_CODES)

    def test_user_cannot_modify_other_users_dca_strategy(self):
        """PATCH on other user's DCA strategy should deny access."""
        response = self.client1.patch(
            f"/api/dca/strategies/{self.user2_strategy.id}/",
            {"name": "Hacked Strategy"},
        )

        self.assertIn(response.status_code, ACCESS_DENIED_CODES)

    def test_user_cannot_delete_other_users_dca_entry(self):
        """DELETE on other user's DCA entry should deny access."""
        response = self.client1.delete(f"/api/dca/entries/{self.user2_entry.id}/")

        self.assertIn(response.status_code, ACCESS_DENIED_CODES)

        self.assertTrue(DCAEntry.objects.filter(id=self.user2_entry.id).exists())


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
    WHITENOISE_AUTOREFRESH=True,
)
class InstallmentRecurringIsolationTests(TestCase):
    """Tests for isolation of installment plans and recurring transactions."""

    def setUp(self):
        """Set up test data."""
        User = get_user_model()

        self.user1 = User.objects.create_user(
            email="user1@test.com", password="testpass123"
        )
        self.client1 = APIClient()
        self.client1.force_authenticate(user=self.user1)

        self.user2 = User.objects.create_user(
            email="user2@test.com", password="testpass123"
        )

        self.currency = Currency.objects.create(
            code="USD", name="US Dollar", decimal_places=2, prefix="$ "
        )

        # User 1's account
        self.user1_account = Account.all_objects.create(
            name="User1 Account", currency=self.currency, owner=self.user1
        )

        # User 2's account
        self.user2_account = Account.all_objects.create(
            name="User2 Account", currency=self.currency, owner=self.user2
        )

        # User 1's installment plan
        self.user1_installment = InstallmentPlan.all_objects.create(
            account=self.user1_account,
            type=Transaction.Type.EXPENSE,
            description="User1 Installment",
            number_of_installments=12,
            start_date=date(2025, 1, 1),
            installment_amount=Decimal("100.00"),
        )

        # User 2's installment plan
        self.user2_installment = InstallmentPlan.all_objects.create(
            account=self.user2_account,
            type=Transaction.Type.EXPENSE,
            description="User2 Installment",
            number_of_installments=6,
            start_date=date(2025, 1, 1),
            installment_amount=Decimal("200.00"),
        )

        # User 1's recurring transaction
        self.user1_recurring = RecurringTransaction.all_objects.create(
            account=self.user1_account,
            type=Transaction.Type.EXPENSE,
            amount=Decimal("50.00"),
            description="User1 Recurring",
            start_date=date(2025, 1, 1),
            recurrence_type=RecurringTransaction.RecurrenceType.MONTH,
            recurrence_interval=1,
        )

        # User 2's recurring transaction
        self.user2_recurring = RecurringTransaction.all_objects.create(
            account=self.user2_account,
            type=Transaction.Type.INCOME,
            amount=Decimal("1000.00"),
            description="User2 Recurring",
            start_date=date(2025, 1, 1),
            recurrence_type=RecurringTransaction.RecurrenceType.MONTH,
            recurrence_interval=1,
        )

    def test_user_cannot_see_other_users_installment_plans(self):
        """GET /api/installment-plans/ should only return user's own plans."""
        response = self.client1.get("/api/installment-plans/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        plan_ids = [p["id"] for p in response.data["results"]]
        self.assertIn(self.user1_installment.id, plan_ids)
        self.assertNotIn(self.user2_installment.id, plan_ids)

    def test_user_cannot_access_other_users_installment_plan_detail(self):
        """GET /api/installment-plans/{id}/ should deny access to other user's plan."""
        response = self.client1.get(
            f"/api/installment-plans/{self.user2_installment.id}/"
        )

        self.assertIn(response.status_code, ACCESS_DENIED_CODES)

    def test_user_cannot_see_other_users_recurring_transactions(self):
        """GET /api/recurring-transactions/ should only return user's own recurring."""
        response = self.client1.get("/api/recurring-transactions/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        recurring_ids = [r["id"] for r in response.data["results"]]
        self.assertIn(self.user1_recurring.id, recurring_ids)
        self.assertNotIn(self.user2_recurring.id, recurring_ids)

    def test_user_cannot_access_other_users_recurring_transaction_detail(self):
        """GET /api/recurring-transactions/{id}/ should deny access to other user's recurring."""
        response = self.client1.get(
            f"/api/recurring-transactions/{self.user2_recurring.id}/"
        )

        self.assertIn(response.status_code, ACCESS_DENIED_CODES)

    def test_user_cannot_modify_other_users_installment_plan(self):
        """PATCH on other user's installment plan should deny access."""
        response = self.client1.patch(
            f"/api/installment-plans/{self.user2_installment.id}/",
            {"description": "Hacked Installment"},
        )

        self.assertIn(response.status_code, ACCESS_DENIED_CODES)

    def test_user_cannot_delete_other_users_recurring_transaction(self):
        """DELETE on other user's recurring transaction should deny access."""
        response = self.client1.delete(
            f"/api/recurring-transactions/{self.user2_recurring.id}/"
        )

        self.assertIn(response.status_code, ACCESS_DENIED_CODES)

        self.assertTrue(
            RecurringTransaction.all_objects.filter(id=self.user2_recurring.id).exists()
        )
