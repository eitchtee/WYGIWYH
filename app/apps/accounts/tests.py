from django.test import TestCase, Client
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.db import IntegrityError, models
from django.utils import timezone
from django.urls import reverse
from decimal import Decimal

from apps.accounts.models import Account, AccountGroup
from apps.currencies.models import Currency
from apps.accounts.forms import AccountForm
from apps.transactions.models import Transaction, TransactionCategory


class AccountTests(TestCase):
    def setUp(self):
        """Set up test data"""
        self.owner1 = User.objects.create_user(username='testowner', password='password123')
        self.client = Client()
        self.client.login(username='testowner', password='password123')

        self.currency = Currency.objects.create(
            code="USD", name="US Dollar", decimal_places=2, prefix="$ "
        )
        self.eur = Currency.objects.create(
            code="EUR", name="Euro", decimal_places=2, prefix="€ "
        )
        self.account_group = AccountGroup.objects.create(name="Test Group", owner=self.owner1)
        self.reconciliation_category = TransactionCategory.objects.create(name='Reconciliation', owner=self.owner1, type='INFO')


    def test_account_creation(self):
        """Test basic account creation"""
        account = Account.objects.create(
            name="Test Account",
            group=self.account_group,
            currency=self.currency,
            is_asset=False,
            is_archived=False,
        )
        self.assertEqual(str(account), "Test Account")
        self.assertEqual(account.name, "Test Account")
        self.assertEqual(account.group, self.account_group)
        self.assertEqual(account.currency, self.currency)
        self.assertFalse(account.is_asset)
        self.assertFalse(account.is_archived)

    def test_account_with_exchange_currency(self):
        """Test account creation with exchange currency"""
        account = Account.objects.create(
            name="Exchange Account",
            owner=self.owner1, # Added owner
            group=self.account_group, # Added group
            currency=self.currency,
            exchange_currency=self.eur, # Changed to self.eur
        )
        self.assertEqual(account.exchange_currency, self.eur) # Changed to self.eur

    def test_account_archiving(self):
        """Test archiving and unarchiving an account"""
        account = Account.objects.create(
            name="Archivable Account",
            owner=self.owner1, # Added owner
            group=self.account_group,
            currency=self.currency,
            is_asset=True, # Assuming default, can be anything for this test
            is_archived=False,
        )
        self.assertFalse(account.is_archived, "Account should initially be unarchived")

        # Archive the account
        account.is_archived = True
        account.save()

        archived_account = Account.objects.get(pk=account.pk)
        self.assertTrue(archived_account.is_archived, "Account should be archived")

        # Unarchive the account
        archived_account.is_archived = False
        archived_account.save()

        unarchived_account = Account.objects.get(pk=account.pk)
        self.assertFalse(unarchived_account.is_archived, "Account should be unarchived")

    def test_account_exchange_currency_cannot_be_same_as_currency(self):
        """Test that exchange_currency cannot be the same as currency."""
        with self.assertRaises(ValidationError) as cm:
            account = Account(
                name="Same Currency Account",
                owner=self.owner1, # Added owner
                group=self.account_group,
                currency=self.currency,
                exchange_currency=self.currency,  # Same as currency
            )
            account.full_clean()
        self.assertIn('exchange_currency', cm.exception.error_dict)
        # To check for a specific message (optional, might make test brittle):
        # self.assertTrue(any("cannot be the same as the main currency" in e.message
        #                     for e in cm.exception.error_dict['exchange_currency']))

    def test_account_name_unique_per_owner(self):
        """Test that account name is unique per owner."""
        owner1 = User.objects.create_user(username='owner1', password='password123')
        owner2 = User.objects.create_user(username='owner2', password='password123')

        # Initial account for self.owner1 (owner1 from setUp)
        Account.objects.create(
            name="Unique Name Test",
            owner=self.owner1, # Changed to self.owner1
            group=self.account_group,
            currency=self.currency,
        )

        # Attempt to create another account with the same name and self.owner1 - should fail
        with self.assertRaises(IntegrityError):
            Account.objects.create(
                name="Unique Name Test",
                owner=self.owner1, # Changed to self.owner1
                group=self.account_group,
                currency=self.currency,
            )

        # Create account with the same name but for owner2 - should succeed
        try:
            Account.objects.create(
                name="Unique Name Test",
                owner=owner2, # owner2 is locally defined here, that's fine for this test
                group=self.account_group,
                currency=self.currency,
            )
        except IntegrityError:
            self.fail("Creating account with same name but different owner failed unexpectedly.")

        # Create account with a different name for self.owner1 - should succeed
        try:
            Account.objects.create(
                name="Another Name Test",
                owner=self.owner1, # Changed to self.owner1
                group=self.account_group,
                currency=self.currency,
            )
        except IntegrityError:
            self.fail("Creating account with different name for the same owner failed unexpectedly.")

    def test_account_form_valid_data(self):
        """Test AccountForm with valid data."""
        form_data = {
            'name': 'Form Test Account',
            'group': self.account_group.pk,
            'currency': self.currency.pk,
            'exchange_currency': self.eur.pk,
            'is_asset': True,
            'is_archived': False,
            'description': 'A valid test account from form.'
        }
        form = AccountForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors.as_text())

        account = form.save(commit=False)
        account.owner = self.owner1
        account.save()

        self.assertEqual(account.name, 'Form Test Account')
        self.assertEqual(account.owner, self.owner1)
        self.assertEqual(account.group, self.account_group)
        self.assertEqual(account.currency, self.currency)
        self.assertEqual(account.exchange_currency, self.eur)
        self.assertTrue(account.is_asset)
        self.assertFalse(account.is_archived)

    def test_account_form_missing_name(self):
        """Test AccountForm with missing name."""
        form_data = {
            'group': self.account_group.pk,
            'currency': self.currency.pk,
        }
        form = AccountForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)

    def test_account_form_exchange_currency_same_as_currency(self):
        """Test AccountForm where exchange_currency is the same as currency."""
        form_data = {
            'name': 'Same Currency Form Account',
            'group': self.account_group.pk,
            'currency': self.currency.pk,
            'exchange_currency': self.currency.pk,  # Same as currency
        }
        form = AccountForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('exchange_currency', form.errors)


class AccountGroupTests(TestCase):
    def setUp(self):
        """Set up test data for AccountGroup tests."""
        self.owner1 = User.objects.create_user(username='groupowner1', password='password123')
        self.owner2 = User.objects.create_user(username='groupowner2', password='password123')

    def test_account_group_creation(self):
        """Test basic AccountGroup creation."""
        group = AccountGroup.objects.create(name="Test Group", owner=self.owner1)
        self.assertEqual(group.name, "Test Group")
        self.assertEqual(group.owner, self.owner1)
        self.assertEqual(str(group), "Test Group") # Assuming __str__ returns the name

    def test_account_group_name_unique_per_owner(self):
        """Test that AccountGroup name is unique per owner."""
        # Initial group for owner1
        AccountGroup.objects.create(name="Unique Group Name", owner=self.owner1)

        # Attempt to create another group with the same name and owner1 - should fail
        with self.assertRaises(IntegrityError):
            AccountGroup.objects.create(name="Unique Group Name", owner=self.owner1)

        # Create group with the same name but for owner2 - should succeed
        try:
            AccountGroup.objects.create(name="Unique Group Name", owner=self.owner2)
        except IntegrityError:
            self.fail("Creating group with same name but different owner failed unexpectedly.")

        # Create group with a different name for owner1 - should succeed
        try:
            AccountGroup.objects.create(name="Another Group Name", owner=self.owner1)
        except IntegrityError:
            self.fail("Creating group with different name for the same owner failed unexpectedly.")

    def test_account_reconciliation_creates_transaction(self):
        """Test that account_reconciliation view creates a transaction for the difference."""

        # Helper function to get balance
        def get_balance(account):
            balance = account.transactions.filter(is_paid=True).aggregate(
                total_income=models.Sum('amount', filter=models.Q(type=Transaction.Type.INCOME)),
                total_expense=models.Sum('amount', filter=models.Q(type=Transaction.Type.EXPENSE)),
                total_transfer_in=models.Sum('amount', filter=models.Q(type=Transaction.Type.TRANSFER, transfer_to_account=account)),
                total_transfer_out=models.Sum('amount', filter=models.Q(type=Transaction.Type.TRANSFER, account=account))
            )['total_income'] or Decimal('0.00')
            balance -= account.transactions.filter(is_paid=True).aggregate(
                total_expense=models.Sum('amount', filter=models.Q(type=Transaction.Type.EXPENSE))
            )['total_expense'] or Decimal('0.00')
            # For transfers, a more complete logic might be needed if transfers are involved in reconciliation scope
            return balance

        account_usd = Account.objects.create(
            name="USD Account for Recon",
            owner=self.owner1,
            currency=self.currency,
            group=self.account_group
        )
        account_eur = Account.objects.create(
            name="EUR Account for Recon",
            owner=self.owner1,
            currency=self.eur,
            group=self.account_group
        )

        # Initial transactions
        Transaction.objects.create(account=account_usd, type=Transaction.Type.INCOME, amount=Decimal('100.00'), date=timezone.localdate(timezone.now()), description='Initial USD', category=self.reconciliation_category, owner=self.owner1, is_paid=True)
        Transaction.objects.create(account=account_eur, type=Transaction.Type.INCOME, amount=Decimal('200.00'), date=timezone.localdate(timezone.now()), description='Initial EUR', category=self.reconciliation_category, owner=self.owner1, is_paid=True)
        Transaction.objects.create(account=account_eur, type=Transaction.Type.EXPENSE, amount=Decimal('50.00'), date=timezone.localdate(timezone.now()), description='EUR Expense', category=self.reconciliation_category, owner=self.owner1, is_paid=True)

        initial_usd_balance = get_balance(account_usd) # Should be 100.00
        initial_eur_balance = get_balance(account_eur) # Should be 150.00
        self.assertEqual(initial_usd_balance, Decimal('100.00'))
        self.assertEqual(initial_eur_balance, Decimal('150.00'))

        initial_transaction_count = Transaction.objects.filter(owner=self.owner1).count() # Should be 3

        formset_data = {
            'form-TOTAL_FORMS': '2',
            'form-INITIAL_FORMS': '2', # Based on view logic, it builds initial data for all accounts
            'form-MAX_NUM_FORMS': '', # Can be empty or a number >= TOTAL_FORMS
            'form-0-account_id': account_usd.id,
            'form-0-new_balance': '120.00', # New balance for USD account (implies +20 adjustment)
            'form-0-category': self.reconciliation_category.id,
            'form-1-account_id': account_eur.id,
            'form-1-new_balance': '150.00', # Same as current balance for EUR account (no adjustment)
            'form-1-category': self.reconciliation_category.id,
        }

        response = self.client.post(
            reverse('accounts:account_reconciliation'),
            data=formset_data,
            HTTP_HX_REQUEST='true' # Required if view uses @only_htmx
        )

        self.assertEqual(response.status_code, 204, response.content.decode()) # 204 No Content for successful HTMX POST

        # Check that only one new transaction was created
        self.assertEqual(Transaction.objects.filter(owner=self.owner1).count(), initial_transaction_count + 1)

        # Get the newly created transaction
        new_transaction = Transaction.objects.filter(
            account=account_usd,
            description="Balance reconciliation"
        ).first()

        self.assertIsNotNone(new_transaction)
        self.assertEqual(new_transaction.type, Transaction.Type.INCOME)
        self.assertEqual(new_transaction.amount, Decimal('20.00'))
        self.assertEqual(new_transaction.category, self.reconciliation_category)
        self.assertEqual(new_transaction.owner, self.owner1)
        self.assertTrue(new_transaction.is_paid)
        self.assertEqual(new_transaction.date, timezone.localdate(timezone.now()))


        # Verify final balances
        self.assertEqual(get_balance(account_usd), Decimal('120.00'))
        self.assertEqual(get_balance(account_eur), Decimal('150.00'))
