from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from django.urls import reverse
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from apps.accounts.models import Account, AccountGroup # Added AccountGroup
from apps.currencies.models import Currency
from apps.transactions.models import TransactionCategory, Transaction
from apps.rules.signals import transaction_created # Assuming this is the correct path

# Default page size for pagination, adjust if your project's default is different
DEFAULT_PAGE_SIZE = 10

class APITestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', email='test@example.com', password='testpassword')
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.currency = Currency.objects.create(code="USD", name="US Dollar Test API", decimal_places=2)
        # Account model requires an AccountGroup
        self.account_group = AccountGroup.objects.create(name="API Test Group", owner=self.user)
        self.account = Account.objects.create(
            name="Test API Account",
            currency=self.currency,
            owner=self.user,
            group=self.account_group
        )
        self.category = TransactionCategory.objects.create(
            name="Test API Category",
            owner=self.user,
            type=TransactionCategory.TransactionType.EXPENSE # Default type, can be adjusted
        )
        # Remove the example test if it's no longer needed or update it
        # self.assertEqual(1 + 1, 2) # from test_example

    def test_transactions_endpoint_authenticated_user(self):
        # User and client are now set up in self.setUp
        url = reverse('api:transaction-list') # Using 'api:' namespace
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    @patch('apps.rules.signals.transaction_created.send')
    def test_create_transaction_api_success(self, mock_signal_send):
        url = reverse('api:transaction-list')
        data = {
            'account': self.account.pk, # Changed from account_id to account to match typical DRF serializer field names
            'type': Transaction.Type.EXPENSE.value, # Use enum value
            'date': date(2023, 1, 15).isoformat(),
            'amount': '123.45',
            'description': 'API Test Expense',
            'category': self.category.pk,
            'tags': [],
            'entities': []
        }

        initial_transaction_count = Transaction.objects.count()
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, 201, response.data) # Print response.data on failure
        self.assertEqual(Transaction.objects.count(), initial_transaction_count + 1)

        created_transaction = Transaction.objects.latest('id') # Get the latest transaction

        self.assertEqual(created_transaction.description, 'API Test Expense')
        self.assertEqual(created_transaction.amount, Decimal('123.45'))
        self.assertEqual(created_transaction.owner, self.user)
        self.assertEqual(created_transaction.account, self.account)
        self.assertEqual(created_transaction.category, self.category)

        mock_signal_send.assert_called_once()
        # Check sender argument of the signal call
        self.assertEqual(mock_signal_send.call_args.kwargs['sender'], Transaction)
        self.assertEqual(mock_signal_send.call_args.kwargs['instance'], created_transaction)


    def test_create_transaction_api_invalid_data(self):
        url = reverse('api:transaction-list')
        data = {
            'account': self.account.pk,
            'type': 'INVALID_TYPE', # Invalid type
            'date': date(2023, 1, 15).isoformat(),
            'amount': 'not_a_number', # Invalid amount
            'description': 'API Test Invalid Data',
            'category': self.category.pk
        }
        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('type', response.data)
        self.assertIn('amount', response.data)

    def test_transaction_list_pagination(self):
        # Create more transactions than page size (e.g., DEFAULT_PAGE_SIZE + 5)
        num_to_create = DEFAULT_PAGE_SIZE + 5
        for i in range(num_to_create):
            Transaction.objects.create(
                account=self.account,
                type=Transaction.Type.EXPENSE,
                date=date(2023, 1, 1) + timedelta(days=i),
                amount=Decimal(f"{10 + i}.00"),
                description=f"Pag Test Transaction {i+1}",
                owner=self.user,
                category=self.category
            )

        url = reverse('api:transaction-list')
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn('count', response.data)
        self.assertEqual(response.data['count'], num_to_create)

        self.assertIn('next', response.data)
        self.assertIsNotNone(response.data['next']) # Assuming count > page size

        self.assertIn('previous', response.data) # Will be None for the first page
        # self.assertIsNone(response.data['previous']) # For the first page

        self.assertIn('results', response.data)
        self.assertEqual(len(response.data['results']), DEFAULT_PAGE_SIZE)
