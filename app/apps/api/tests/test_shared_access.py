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
class SharedAccountAccessTests(TestCase):
    """Tests for shared account access via shared_with field."""

    def setUp(self):
        """Set up test data with shared accounts."""
        User = get_user_model()

        # User 1 - owner
        self.user1 = User.objects.create_user(
            email="user1@test.com", password="testpass123"
        )
        self.client1 = APIClient()
        self.client1.force_authenticate(user=self.user1)

        # User 2 - will have shared access
        self.user2 = User.objects.create_user(
            email="user2@test.com", password="testpass123"
        )
        self.client2 = APIClient()
        self.client2.force_authenticate(user=self.user2)

        # User 3 - no shared access
        self.user3 = User.objects.create_user(
            email="user3@test.com", password="testpass123"
        )
        self.client3 = APIClient()
        self.client3.force_authenticate(user=self.user3)

        self.currency = Currency.objects.create(
            code="USD", name="US Dollar", decimal_places=2, prefix="$ "
        )

        # User 1's account shared with user 2
        self.shared_account = Account.all_objects.create(
            name="Shared Account",
            currency=self.currency,
            owner=self.user1,
            visibility="private",
        )
        self.shared_account.shared_with.add(self.user2)

        # User 1's private account (not shared)
        self.private_account = Account.all_objects.create(
            name="Private Account",
            currency=self.currency,
            owner=self.user1,
            visibility="private",
        )

        # Transaction in shared account
        self.shared_transaction = Transaction.userless_all_objects.create(
            account=self.shared_account,
            type=Transaction.Type.INCOME,
            amount=Decimal("100.00"),
            is_paid=True,
            date=date(2025, 1, 1),
            description="Shared Transaction",
            owner=self.user1,
        )

        # Transaction in private account
        self.private_transaction = Transaction.userless_all_objects.create(
            account=self.private_account,
            type=Transaction.Type.EXPENSE,
            amount=Decimal("50.00"),
            is_paid=True,
            date=date(2025, 1, 1),
            description="Private Transaction",
            owner=self.user1,
        )

    def test_user_can_see_accounts_shared_with_them(self):
        """User2 should see the account shared with them."""
        response = self.client2.get("/api/accounts/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        account_ids = [acc["id"] for acc in response.data["results"]]
        self.assertIn(self.shared_account.id, account_ids)

    def test_user_cannot_see_accounts_not_shared_with_them(self):
        """User2 should NOT see user1's private (non-shared) account."""
        response = self.client2.get("/api/accounts/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        account_ids = [acc["id"] for acc in response.data["results"]]
        self.assertNotIn(self.private_account.id, account_ids)

    def test_user_can_access_shared_account_detail(self):
        """User2 should be able to access shared account details."""
        response = self.client2.get(f"/api/accounts/{self.shared_account.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Shared Account")

    def test_user_without_share_cannot_access_shared_account(self):
        """User3 should NOT be able to access the shared account."""
        response = self.client3.get(f"/api/accounts/{self.shared_account.id}/")

        self.assertIn(response.status_code, ACCESS_DENIED_CODES)

    def test_user_can_see_transactions_in_shared_account(self):
        """User2 should see transactions in the shared account."""
        response = self.client2.get("/api/transactions/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        transaction_ids = [t["id"] for t in response.data["results"]]
        self.assertIn(self.shared_transaction.id, transaction_ids)
        self.assertNotIn(self.private_transaction.id, transaction_ids)

    def test_user_can_access_transaction_in_shared_account(self):
        """User2 should be able to access transaction details in shared account."""
        response = self.client2.get(f"/api/transactions/{self.shared_transaction.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["description"], "Shared Transaction")

    def test_user_cannot_access_transaction_in_non_shared_account(self):
        """User2 should NOT access transactions in user1's private account."""
        response = self.client2.get(f"/api/transactions/{self.private_transaction.id}/")

        self.assertIn(response.status_code, ACCESS_DENIED_CODES)

    def test_user_can_get_balance_of_shared_account(self):
        """User2 should be able to get balance of shared account."""
        response = self.client2.get(f"/api/accounts/{self.shared_account.id}/balance/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("current_balance", response.data)

    def test_sharing_works_with_multiple_users(self):
        """Account shared with multiple users should be accessible by all."""
        # Add user3 to shared_with
        self.shared_account.shared_with.add(self.user3)

        # User2 still has access
        response2 = self.client2.get(f"/api/accounts/{self.shared_account.id}/")
        self.assertEqual(response2.status_code, status.HTTP_200_OK)

        # User3 now has access
        response3 = self.client3.get(f"/api/accounts/{self.shared_account.id}/")
        self.assertEqual(response3.status_code, status.HTTP_200_OK)


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
    WHITENOISE_AUTOREFRESH=True,
)
class PublicVisibilityTests(TestCase):
    """Tests for public visibility access."""

    def setUp(self):
        """Set up test data with public accounts."""
        User = get_user_model()

        self.user1 = User.objects.create_user(
            email="user1@test.com", password="testpass123"
        )
        self.client1 = APIClient()
        self.client1.force_authenticate(user=self.user1)

        self.user2 = User.objects.create_user(
            email="user2@test.com", password="testpass123"
        )
        self.client2 = APIClient()
        self.client2.force_authenticate(user=self.user2)

        self.currency = Currency.objects.create(
            code="USD", name="US Dollar", decimal_places=2, prefix="$ "
        )

        # User 1's public account
        self.public_account = Account.all_objects.create(
            name="Public Account",
            currency=self.currency,
            owner=self.user1,
            visibility="public",
        )

        # User 1's private account
        self.private_account = Account.all_objects.create(
            name="Private Account",
            currency=self.currency,
            owner=self.user1,
            visibility="private",
        )

        # Transaction in public account
        self.public_transaction = Transaction.userless_all_objects.create(
            account=self.public_account,
            type=Transaction.Type.INCOME,
            amount=Decimal("100.00"),
            is_paid=True,
            date=date(2025, 1, 1),
            description="Public Transaction",
            owner=self.user1,
        )

    def test_user_can_see_public_accounts(self):
        """User2 should see user1's public account."""
        response = self.client2.get("/api/accounts/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        account_ids = [acc["id"] for acc in response.data["results"]]
        self.assertIn(self.public_account.id, account_ids)
        self.assertNotIn(self.private_account.id, account_ids)

    def test_user_can_access_public_account_detail(self):
        """User2 should be able to access public account details."""
        response = self.client2.get(f"/api/accounts/{self.public_account.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Public Account")

    def test_user_can_see_transactions_in_public_accounts(self):
        """User2 should see transactions in public accounts."""
        response = self.client2.get("/api/transactions/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        transaction_ids = [t["id"] for t in response.data["results"]]
        self.assertIn(self.public_transaction.id, transaction_ids)


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
    WHITENOISE_AUTOREFRESH=True,
)
class SharedCategoryTagEntityTests(TestCase):
    """Tests for shared categories, tags, and entities."""

    def setUp(self):
        """Set up test data with shared categories/tags/entities."""
        User = get_user_model()

        self.user1 = User.objects.create_user(
            email="user1@test.com", password="testpass123"
        )
        self.client1 = APIClient()
        self.client1.force_authenticate(user=self.user1)

        self.user2 = User.objects.create_user(
            email="user2@test.com", password="testpass123"
        )
        self.client2 = APIClient()
        self.client2.force_authenticate(user=self.user2)

        self.user3 = User.objects.create_user(
            email="user3@test.com", password="testpass123"
        )
        self.client3 = APIClient()
        self.client3.force_authenticate(user=self.user3)

        # User 1's category shared with user 2
        self.shared_category = TransactionCategory.all_objects.create(
            name="Shared Category", owner=self.user1
        )
        self.shared_category.shared_with.add(self.user2)

        # User 1's private category
        self.private_category = TransactionCategory.all_objects.create(
            name="Private Category", owner=self.user1
        )

        # User 1's public category
        self.public_category = TransactionCategory.all_objects.create(
            name="Public Category", owner=self.user1, visibility="public"
        )

        # User 1's tag shared with user 2
        self.shared_tag = TransactionTag.all_objects.create(
            name="Shared Tag", owner=self.user1
        )
        self.shared_tag.shared_with.add(self.user2)

        # User 1's entity shared with user 2
        self.shared_entity = TransactionEntity.all_objects.create(
            name="Shared Entity", owner=self.user1
        )
        self.shared_entity.shared_with.add(self.user2)

    def test_user_can_see_shared_categories(self):
        """User2 should see categories shared with them."""
        response = self.client2.get("/api/categories/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        category_ids = [c["id"] for c in response.data["results"]]
        self.assertIn(self.shared_category.id, category_ids)
        self.assertNotIn(self.private_category.id, category_ids)

    def test_user_can_access_shared_category_detail(self):
        """User2 should be able to access shared category details."""
        response = self.client2.get(f"/api/categories/{self.shared_category.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Shared Category")

    def test_user_can_see_public_categories(self):
        """User3 should see public categories."""
        response = self.client3.get("/api/categories/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        category_ids = [c["id"] for c in response.data["results"]]
        self.assertIn(self.public_category.id, category_ids)

    def test_user_without_share_cannot_see_shared_category(self):
        """User3 should NOT see category shared only with user2."""
        response = self.client3.get("/api/categories/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        category_ids = [c["id"] for c in response.data["results"]]
        self.assertNotIn(self.shared_category.id, category_ids)

    def test_user_can_see_shared_tags(self):
        """User2 should see tags shared with them."""
        response = self.client2.get("/api/tags/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        tag_ids = [t["id"] for t in response.data["results"]]
        self.assertIn(self.shared_tag.id, tag_ids)

    def test_user_can_access_shared_tag_detail(self):
        """User2 should be able to access shared tag details."""
        response = self.client2.get(f"/api/tags/{self.shared_tag.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Shared Tag")

    def test_user_can_see_shared_entities(self):
        """User2 should see entities shared with them."""
        response = self.client2.get("/api/entities/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        entity_ids = [e["id"] for e in response.data["results"]]
        self.assertIn(self.shared_entity.id, entity_ids)

    def test_user_can_access_shared_entity_detail(self):
        """User2 should be able to access shared entity details."""
        response = self.client2.get(f"/api/entities/{self.shared_entity.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Shared Entity")


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
    WHITENOISE_AUTOREFRESH=True,
)
class SharedDCAAccessTests(TestCase):
    """Tests for shared DCA strategy access."""

    def setUp(self):
        """Set up test data with shared DCA strategies."""
        User = get_user_model()

        self.user1 = User.objects.create_user(
            email="user1@test.com", password="testpass123"
        )
        self.client1 = APIClient()
        self.client1.force_authenticate(user=self.user1)

        self.user2 = User.objects.create_user(
            email="user2@test.com", password="testpass123"
        )
        self.client2 = APIClient()
        self.client2.force_authenticate(user=self.user2)

        self.user3 = User.objects.create_user(
            email="user3@test.com", password="testpass123"
        )
        self.client3 = APIClient()
        self.client3.force_authenticate(user=self.user3)

        self.currency1 = Currency.objects.create(
            code="BTC", name="Bitcoin", decimal_places=8, prefix=""
        )
        self.currency2 = Currency.objects.create(
            code="USD", name="US Dollar", decimal_places=2, prefix="$ "
        )

        # User 1's DCA strategy shared with user 2
        self.shared_strategy = DCAStrategy.all_objects.create(
            name="Shared BTC Strategy",
            target_currency=self.currency1,
            payment_currency=self.currency2,
            owner=self.user1,
        )
        self.shared_strategy.shared_with.add(self.user2)

        # Entry in shared strategy
        self.shared_entry = DCAEntry.objects.create(
            strategy=self.shared_strategy,
            date=date(2025, 1, 1),
            amount_paid=Decimal("100.00"),
            amount_received=Decimal("0.001"),
        )

        # User 1's private strategy
        self.private_strategy = DCAStrategy.all_objects.create(
            name="Private BTC Strategy",
            target_currency=self.currency1,
            payment_currency=self.currency2,
            owner=self.user1,
        )

    def test_user_can_see_shared_dca_strategies(self):
        """User2 should see DCA strategies shared with them."""
        response = self.client2.get("/api/dca/strategies/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        strategy_ids = [s["id"] for s in response.data["results"]]
        self.assertIn(self.shared_strategy.id, strategy_ids)
        self.assertNotIn(self.private_strategy.id, strategy_ids)

    def test_user_can_access_shared_dca_strategy_detail(self):
        """User2 should be able to access shared strategy details."""
        response = self.client2.get(f"/api/dca/strategies/{self.shared_strategy.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Shared BTC Strategy")

    def test_user_without_share_cannot_see_shared_strategy(self):
        """User3 should NOT see strategy shared only with user2."""
        response = self.client3.get("/api/dca/strategies/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        strategy_ids = [s["id"] for s in response.data["results"]]
        self.assertNotIn(self.shared_strategy.id, strategy_ids)

    def test_user_can_access_shared_strategy_actions(self):
        """User2 should be able to access actions on shared strategy."""
        # investment_frequency
        response1 = self.client2.get(
            f"/api/dca/strategies/{self.shared_strategy.id}/investment_frequency/"
        )
        self.assertEqual(response1.status_code, status.HTTP_200_OK)

        # price_comparison
        response2 = self.client2.get(
            f"/api/dca/strategies/{self.shared_strategy.id}/price_comparison/"
        )
        self.assertEqual(response2.status_code, status.HTTP_200_OK)

        # current_price
        response3 = self.client2.get(
            f"/api/dca/strategies/{self.shared_strategy.id}/current_price/"
        )
        self.assertEqual(response3.status_code, status.HTTP_200_OK)


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
    WHITENOISE_AUTOREFRESH=True,
)
class SharedAccountGroupTests(TestCase):
    """Tests for shared account group access."""

    def setUp(self):
        """Set up test data with shared account groups."""
        User = get_user_model()

        self.user1 = User.objects.create_user(
            email="user1@test.com", password="testpass123"
        )
        self.client1 = APIClient()
        self.client1.force_authenticate(user=self.user1)

        self.user2 = User.objects.create_user(
            email="user2@test.com", password="testpass123"
        )
        self.client2 = APIClient()
        self.client2.force_authenticate(user=self.user2)

        self.user3 = User.objects.create_user(
            email="user3@test.com", password="testpass123"
        )
        self.client3 = APIClient()
        self.client3.force_authenticate(user=self.user3)

        # User 1's account group shared with user 2
        self.shared_group = AccountGroup.all_objects.create(
            name="Shared Group", owner=self.user1
        )
        self.shared_group.shared_with.add(self.user2)

        # User 1's private account group
        self.private_group = AccountGroup.all_objects.create(
            name="Private Group", owner=self.user1
        )

        # User 1's public account group
        self.public_group = AccountGroup.all_objects.create(
            name="Public Group", owner=self.user1, visibility="public"
        )

    def test_user_can_see_shared_account_groups(self):
        """User2 should see account groups shared with them."""
        response = self.client2.get("/api/account-groups/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        group_ids = [g["id"] for g in response.data["results"]]
        self.assertIn(self.shared_group.id, group_ids)
        self.assertNotIn(self.private_group.id, group_ids)

    def test_user_can_access_shared_account_group_detail(self):
        """User2 should be able to access shared account group details."""
        response = self.client2.get(f"/api/account-groups/{self.shared_group.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Shared Group")

    def test_user_can_see_public_account_groups(self):
        """User3 should see public account groups."""
        response = self.client3.get("/api/account-groups/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        group_ids = [g["id"] for g in response.data["results"]]
        self.assertIn(self.public_group.id, group_ids)

    def test_user_without_share_cannot_access_shared_group(self):
        """User3 should NOT be able to access shared account group."""
        response = self.client3.get(f"/api/account-groups/{self.shared_group.id}/")

        self.assertIn(response.status_code, ACCESS_DENIED_CODES)
