from decimal import Decimal
from datetime import date, datetime
from unittest.mock import patch

from django.urls import reverse
from django.contrib.auth import get_user_model
from django.conf import settings
from rest_framework.test import APIClient, APITestCase # APITestCase handles DB setup better for API tests
from rest_framework import status

from apps.accounts.models import Account, AccountGroup
from apps.currencies.models import Currency
from apps.transactions.models import Transaction, TransactionCategory, TransactionTag, TransactionEntity
# Assuming thread_local is used for setting user for serializers if they auto-assign owner
from apps.common.middleware.thread_local import set_current_user

User = get_user_model()

class BaseAPITestCase(APITestCase): # Use APITestCase for DRF tests
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="apiuser@example.com", password="password")
        cls.superuser = User.objects.create_superuser(email="apisuper@example.com", password="password")

        cls.currency_usd = Currency.objects.create(code="USD", name="US Dollar API", decimal_places=2)
        cls.account_group_api = AccountGroup.objects.create(name="API Group", owner=cls.user)
        cls.account_usd_api = Account.objects.create(
            name="API Checking USD", currency=cls.currency_usd, owner=cls.user, group=cls.account_group_api
        )
        cls.category_api = TransactionCategory.objects.create(name="API Food", owner=cls.user)
        cls.tag_api = TransactionTag.objects.create(name="API Urgent", owner=cls.user)
        cls.entity_api = TransactionEntity.objects.create(name="API Store", owner=cls.user)

    def setUp(self):
        self.client = APIClient()
        # Authenticate as regular user by default, can be overridden in tests
        self.client.force_authenticate(user=self.user)
        set_current_user(self.user) # For serializers/models that might use get_current_user

    def tearDown(self):
        set_current_user(None)


class TransactionAPITests(BaseAPITestCase):
    def test_list_transactions(self):
        # Create a transaction for the authenticated user
        Transaction.objects.create(
            account=self.account_usd_api, owner=self.user, type=Transaction.Type.EXPENSE,
            date=date(2023, 1, 1), amount=Decimal("10.00"), description="Test List"
        )
        url = reverse("transaction-list") # DRF default router name
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["pagination"]["count"], 1)
        self.assertEqual(response.data["results"][0]["description"], "Test List")

    def test_retrieve_transaction(self):
        t = Transaction.objects.create(
            account=self.account_usd_api, owner=self.user, type=Transaction.Type.INCOME,
            date=date(2023, 2, 1), amount=Decimal("100.00"), description="Specific Salary"
        )
        url = reverse("transaction-detail", kwargs={'pk': t.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["description"], "Specific Salary")
        self.assertIn("exchanged_amount", response.data) # Check for SerializerMethodField

    @patch('apps.transactions.signals.transaction_created.send')
    def test_create_transaction(self, mock_signal_send):
        url = reverse("transaction-list")
        data = {
            "account_id": self.account_usd_api.pk,
            "type": Transaction.Type.EXPENSE,
            "date": "2023-03-01",
            "reference_date": "2023-03", # Test custom format
            "amount": "25.50",
            "description": "New API Expense",
            "category": self.category_api.name, # Assuming TransactionCategoryField handles name to instance
            "tags": [self.tag_api.name],       # Assuming TransactionTagField handles list of names
            "entities": [self.entity_api.name] # Assuming TransactionEntityField handles list of names
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(Transaction.objects.filter(description="New API Expense").exists())

        created_transaction = Transaction.objects.get(description="New API Expense")
        self.assertEqual(created_transaction.owner, self.user) # Check if owner is set
        self.assertEqual(created_transaction.category.name, self.category_api.name)
        self.assertIn(self.tag_api, created_transaction.tags.all())
        mock_signal_send.assert_called_once()


    def test_create_transaction_missing_fields(self):
        url = reverse("transaction-list")
        data = {"account_id": self.account_usd_api.pk, "type": Transaction.Type.EXPENSE} # Missing date, amount, desc
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("date", response.data) # Or reference_date due to custom validate
        self.assertIn("amount", response.data)
        self.assertIn("description", response.data)

    @patch('apps.transactions.signals.transaction_updated.send')
    def test_update_transaction_put(self, mock_signal_send):
        t = Transaction.objects.create(
            account=self.account_usd_api, owner=self.user, type=Transaction.Type.EXPENSE,
            date=date(2023, 4, 1), amount=Decimal("50.00"), description="Initial PUT"
        )
        url = reverse("transaction-detail", kwargs={'pk': t.pk})
        data = {
            "account_id": self.account_usd_api.pk,
            "type": Transaction.Type.INCOME, # Changed type
            "date": "2023-04-05",           # Changed date
            "amount": "75.00",              # Changed amount
            "description": "Updated PUT Transaction",
            "category": self.category_api.name
        }
        response = self.client.put(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        t.refresh_from_db()
        self.assertEqual(t.description, "Updated PUT Transaction")
        self.assertEqual(t.type, Transaction.Type.INCOME)
        self.assertEqual(t.amount, Decimal("75.00"))
        mock_signal_send.assert_called_once()

    @patch('apps.transactions.signals.transaction_updated.send')
    def test_update_transaction_patch(self, mock_signal_send):
        t = Transaction.objects.create(
            account=self.account_usd_api, owner=self.user, type=Transaction.Type.EXPENSE,
            date=date(2023, 5, 1), amount=Decimal("30.00"), description="Initial PATCH"
        )
        url = reverse("transaction-detail", kwargs={'pk': t.pk})
        data = {"description": "Patched Description"}
        response = self.client.patch(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        t.refresh_from_db()
        self.assertEqual(t.description, "Patched Description")
        mock_signal_send.assert_called_once()


    def test_delete_transaction(self):
        t = Transaction.objects.create(
            account=self.account_usd_api, owner=self.user, type=Transaction.Type.EXPENSE,
            date=date(2023, 6, 1), amount=Decimal("10.00"), description="To Delete"
        )
        url = reverse("transaction-detail", kwargs={'pk': t.pk})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        # Default manager should not find it (soft delete)
        self.assertFalse(Transaction.objects.filter(pk=t.pk).exists())
        self.assertTrue(Transaction.all_objects.filter(pk=t.pk, deleted=True).exists())


class AccountAPITests(BaseAPITestCase):
    def test_list_accounts(self):
        url = reverse("account-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # setUp creates one account (self.account_usd_api) for self.user
        self.assertEqual(response.data["pagination"]["count"], 1)
        self.assertEqual(response.data["results"][0]["name"], self.account_usd_api.name)

    def test_create_account(self):
        url = reverse("account-list")
        data = {
            "name": "API Savings EUR",
            "currency_id": self.currency_eur.pk,
            "group_id": self.account_group_api.pk,
            "is_asset": False
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(Account.objects.filter(name="API Savings EUR", owner=self.user).exists())

# --- Permission Tests ---
class APIPermissionTests(BaseAPITestCase):
    def test_not_in_demo_mode_permission_regular_user(self):
        # Temporarily activate demo mode
        with self.settings(DEMO=True):
            url = reverse("transaction-list")
            # Attempt POST as regular user (self.user is not superuser)
            response = self.client.post(url, {"description": "test"}, format='json')
            # This depends on default permissions. If IsAuthenticated allows POST, NotInDemoMode should deny.
            # If default is ReadOnly, then GET would be allowed, POST denied regardless of NotInDemoMode for non-admin.
            # Assuming NotInDemoMode is a primary gate for write operations.
            # The permission itself doesn't check request.method, just user status in demo.
            # So, even GET might be denied if NotInDemoMode were the *only* permission.
            # However, ViewSets usually have IsAuthenticated or similar allowing GET.
            # Let's assume NotInDemoMode is added to default_permission_classes and tested on a write view.
            # For a POST to transactions:
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

            # GET should still be allowed if default permissions allow it (e.g. IsAuthenticatedOrReadOnly)
            # and NotInDemoMode only blocks mutating methods or specific views.
            # The current NotInDemoMode blocks *all* access for non-superusers in demo.
            get_response = self.client.get(url)
            self.assertEqual(get_response.status_code, status.HTTP_403_FORBIDDEN)


    def test_not_in_demo_mode_permission_superuser(self):
        self.client.force_authenticate(user=self.superuser)
        set_current_user(self.superuser)
        with self.settings(DEMO=True):
            url = reverse("transaction-list")
            data = { # Valid data for transaction creation
                "account_id": self.account_usd_api.pk, "type": Transaction.Type.EXPENSE,
                "date": "2023-07-01", "amount": "1.00", "description": "Superuser Demo Post"
            }
            response = self.client.post(url, data, format='json')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

            get_response = self.client.get(url)
            self.assertEqual(get_response.status_code, status.HTTP_200_OK)


    def test_access_in_non_demo_mode(self):
        with self.settings(DEMO=False): # Explicitly ensure demo mode is off
            url = reverse("transaction-list")
            data = {
                "account_id": self.account_usd_api.pk, "type": Transaction.Type.EXPENSE,
                "date": "2023-08-01", "amount": "2.00", "description": "Non-Demo Post"
            }
            response = self.client.post(url, data, format='json')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

            get_response = self.client.get(url)
            self.assertEqual(get_response.status_code, status.HTTP_200_OK)

    def test_unauthenticated_access(self):
        self.client.logout() # Or self.client.force_authenticate(user=None)
        set_current_user(None)
        url = reverse("transaction-list")
        response = self.client.get(url)
        # Default behavior for DRF is IsAuthenticated, so should be 401 or 403
        # If IsAuthenticatedOrReadOnly, GET would be 200.
        # Given serializers specify IsAuthenticated, likely 401/403.
        self.assertTrue(response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

# TODO: Add tests for pagination by providing `?page=X` and `?page_size=Y`
# TODO: Add tests for filtering if specific filter_backends are configured on ViewSets.
# TODO: Add tests for other ViewSets (Categories, Tags, Accounts, etc.)
# TODO: Test custom serializer fields like TransactionCategoryField more directly if their logic is complex.
# (e.g., creating category by name if it doesn't exist vs. only allowing existing by ID)
# The current create test for transactions implicitly tests this behavior.
```
