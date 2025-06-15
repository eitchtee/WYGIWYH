from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.forms import NON_FIELD_ERRORS
from apps.currencies.models import Currency
from apps.dca.models import DCAStrategy, DCAEntry
from apps.dca.forms import DCAStrategyForm, DCAEntryForm # Added DCAEntryForm
from apps.accounts.models import Account, AccountGroup # Added Account models
from apps.transactions.models import TransactionCategory, Transaction # Added Transaction models
from decimal import Decimal
from datetime import date
from unittest.mock import patch

class DCATests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='testowner', password='password123')
        self.client = Client()
        self.client.login(username='testowner', password='password123')

        self.payment_curr = Currency.objects.create(code="USD", name="US Dollar", decimal_places=2)
        self.target_curr = Currency.objects.create(code="BTC", name="Bitcoin", decimal_places=8)

        # AccountGroup for accounts
        self.account_group = AccountGroup.objects.create(name="DCA Test Group", owner=self.owner)

        # Accounts for transactions
        self.account1 = Account.objects.create(
            name="Payment Account USD",
            owner=self.owner,
            currency=self.payment_curr,
            group=self.account_group
        )
        self.account2 = Account.objects.create(
            name="Target Account BTC",
            owner=self.owner,
            currency=self.target_curr,
            group=self.account_group
        )

        # TransactionCategory for transactions
        # Using INFO type as it's generic. TRANSFER might imply specific paired transaction logic not relevant here.
        self.category1 = TransactionCategory.objects.create(
            name="DCA Category",
            owner=self.owner,
            type=TransactionCategory.TransactionType.INFO
        )


        self.strategy1 = DCAStrategy.objects.create(
            name="Test Strategy 1",
            owner=self.owner,
            payment_currency=self.payment_curr,
            target_currency=self.target_curr
        )

        self.entries1 = [
            DCAEntry.objects.create(
                strategy=self.strategy1,
                date=date(2023, 1, 1),
                amount_paid=Decimal('100.00'),
                amount_received=Decimal('0.010')
            ),
            DCAEntry.objects.create(
                strategy=self.strategy1,
                date=date(2023, 2, 1),
                amount_paid=Decimal('150.00'),
                amount_received=Decimal('0.012')
            ),
            DCAEntry.objects.create(
                strategy=self.strategy1,
                date=date(2023, 3, 1),
                amount_paid=Decimal('120.00'),
                amount_received=Decimal('0.008')
            )
        ]

    def test_strategy_index_view_authenticated_user(self):
        # Uses self.client and self.owner from setUp
        response = self.client.get(reverse('dca:dca_strategy_index'))
        self.assertEqual(response.status_code, 200)

    def test_strategy_totals_and_average_price(self):
        self.assertEqual(self.strategy1.total_entries(), 3)
        self.assertEqual(self.strategy1.total_invested(), Decimal('370.00')) # 100 + 150 + 120
        self.assertEqual(self.strategy1.total_received(), Decimal('0.030'))  # 0.01 + 0.012 + 0.008

        expected_avg_price = Decimal('370.00') / Decimal('0.030')
        # Match precision of the model method if it's specific, e.g. quantize
        # For now, direct comparison. The model might return a Decimal that needs specific quantizing.
        self.assertEqual(self.strategy1.average_entry_price(), expected_avg_price)

    def test_strategy_average_price_no_received(self):
        strategy2 = DCAStrategy.objects.create(
            name="Test Strategy 2",
            owner=self.owner,
            payment_currency=self.payment_curr,
            target_currency=self.target_curr
        )
        DCAEntry.objects.create(
            strategy=strategy2,
            date=date(2023, 4, 1),
            amount_paid=Decimal('100.00'),
            amount_received=Decimal('0') # Total received is zero
        )
        self.assertEqual(strategy2.total_received(), Decimal('0'))
        self.assertEqual(strategy2.average_entry_price(), Decimal('0'))

    @patch('apps.dca.models.convert')
    def test_dca_entry_value_and_pl(self, mock_convert):
        entry = self.entries1[0] # amount_paid=100, amount_received=0.010

        # Simulate current price: 1 target_curr = 20,000 payment_curr
        # So, 0.010 target_curr should be 0.010 * 20000 = 200 payment_curr
        simulated_converted_value = entry.amount_received * Decimal('20000')
        mock_convert.return_value = (
            simulated_converted_value,
            self.payment_curr.prefix,
            self.payment_curr.suffix,
            self.payment_curr.decimal_places
        )

        current_val = entry.current_value()
        self.assertEqual(current_val, Decimal('200.00'))

        # Profit/Loss = current_value - amount_paid = 200 - 100 = 100
        self.assertEqual(entry.profit_loss(), Decimal('100.00'))

        # P/L % = (profit_loss / amount_paid) * 100 = (100 / 100) * 100 = 100
        self.assertEqual(entry.profit_loss_percentage(), Decimal('100.00'))

        # Check that convert was called correctly by current_value()
        # current_value calls convert(self.amount_received, self.strategy.target_currency, self.strategy.payment_currency)
        # The date argument defaults to None if not passed, which is the case here.
        mock_convert.assert_called_once_with(
            entry.amount_received,
            self.strategy1.target_currency,
            self.strategy1.payment_currency,
            None # Date argument is optional and defaults to None
        )

    @patch('apps.dca.models.convert')
    def test_dca_strategy_value_and_pl(self, mock_convert):

        def side_effect_func(amount_to_convert, from_currency, to_currency, date=None):
            if from_currency == self.target_curr and to_currency == self.payment_curr:
                # Simulate current price: 1 target_curr = 20,000 payment_curr
                converted_value = amount_to_convert * Decimal('20000')
                return (converted_value, self.payment_curr.prefix, self.payment_curr.suffix, self.payment_curr.decimal_places)
            # Fallback for any other unexpected calls, though not expected in this test
            return (Decimal('0'), '', '', 2)

        mock_convert.side_effect = side_effect_func

        # strategy1 entries:
        # 1: paid 100, received 0.010. Current value = 0.010 * 20000 = 200
        # 2: paid 150, received 0.012. Current value = 0.012 * 20000 = 240
        # 3: paid 120, received 0.008. Current value = 0.008 * 20000 = 160
        # Total current value = 200 + 240 + 160 = 600
        self.assertEqual(self.strategy1.current_total_value(), Decimal('600.00'))

        # Total invested = 100 + 150 + 120 = 370
        # Total profit/loss = current_total_value - total_invested = 600 - 370 = 230
        self.assertEqual(self.strategy1.total_profit_loss(), Decimal('230.00'))

        # Total P/L % = (total_profit_loss / total_invested) * 100
        # (230 / 370) * 100 = 62.162162...
        expected_pl_percentage = (Decimal('230.00') / Decimal('370.00')) * Decimal('100')
        self.assertAlmostEqual(self.strategy1.total_profit_loss_percentage(), expected_pl_percentage, places=2)

    def test_dca_strategy_form_valid_data(self):
        form_data = {
            'name': 'Form Test Strategy',
            'target_currency': self.target_curr.pk,
            'payment_currency': self.payment_curr.pk
        }
        form = DCAStrategyForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors.as_text())

        strategy = form.save(commit=False)
        strategy.owner = self.owner
        strategy.save()

        self.assertEqual(strategy.name, 'Form Test Strategy')
        self.assertEqual(strategy.owner, self.owner)
        self.assertEqual(strategy.target_currency, self.target_curr)
        self.assertEqual(strategy.payment_currency, self.payment_curr)

    def test_dca_strategy_form_missing_name(self):
        form_data = {
            'target_currency': self.target_curr.pk,
            'payment_currency': self.payment_curr.pk
        }
        form = DCAStrategyForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('name', form.errors)

    def test_dca_strategy_form_missing_target_currency(self):
        form_data = {
            'name': 'Form Test Missing Target',
            'payment_currency': self.payment_curr.pk
        }
        form = DCAStrategyForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('target_currency', form.errors)

    # Tests for DCAEntryForm clean method
    def test_dca_entry_form_clean_create_transaction_missing_accounts(self):
        data = {
            'date': date(2023, 1, 1),
            'amount_paid': Decimal('100.00'),
            'amount_received': Decimal('0.01'),
            'create_transaction': True,
            # from_account and to_account are missing
        }
        form = DCAEntryForm(data=data, strategy=self.strategy1, owner=self.owner)
        self.assertFalse(form.is_valid())
        self.assertIn('from_account', form.errors)
        self.assertIn('to_account', form.errors)

    def test_dca_entry_form_clean_create_transaction_same_accounts(self):
        data = {
            'date': date(2023, 1, 1),
            'amount_paid': Decimal('100.00'),
            'amount_received': Decimal('0.01'),
            'create_transaction': True,
            'from_account': self.account1.pk,
            'to_account': self.account1.pk, # Same as from_account
            'from_category': self.category1.pk,
            'to_category': self.category1.pk,
        }
        form = DCAEntryForm(data=data, strategy=self.strategy1, owner=self.owner)
        self.assertFalse(form.is_valid())
        # Check for non-field error or specific field error based on form implementation
        self.assertTrue(NON_FIELD_ERRORS in form.errors or 'to_account' in form.errors)
        if NON_FIELD_ERRORS in form.errors:
             self.assertTrue(any("From and To accounts must be different" in error for error in form.errors[NON_FIELD_ERRORS]))


    # Tests for DCAEntryForm save method
    def test_dca_entry_form_save_create_transactions(self):
        data = {
            'date': date(2023, 5, 1),
            'amount_paid': Decimal('200.00'),
            'amount_received': Decimal('0.025'),
            'create_transaction': True,
            'from_account': self.account1.pk,
            'to_account': self.account2.pk,
            'from_category': self.category1.pk,
            'to_category': self.category1.pk,
            'description': 'Test DCA entry transaction creation'
        }
        form = DCAEntryForm(data=data, strategy=self.strategy1, owner=self.owner)

        if not form.is_valid():
            print(form.errors.as_json()) # Print errors if form is invalid
        self.assertTrue(form.is_valid())

        entry = form.save()

        self.assertIsNotNone(entry.pk)
        self.assertEqual(entry.strategy, self.strategy1)
        self.assertIsNotNone(entry.expense_transaction)
        self.assertIsNotNone(entry.income_transaction)

        # Check expense transaction
        expense_tx = entry.expense_transaction
        self.assertEqual(expense_tx.account, self.account1)
        self.assertEqual(expense_tx.type, Transaction.Type.EXPENSE)
        self.assertEqual(expense_tx.amount, data['amount_paid'])
        self.assertEqual(expense_tx.category, self.category1)
        self.assertEqual(expense_tx.owner, self.owner)
        self.assertEqual(expense_tx.date, data['date'])
        self.assertIn(str(entry.id)[:8], expense_tx.description) # Check if part of entry ID is in description

        # Check income transaction
        income_tx = entry.income_transaction
        self.assertEqual(income_tx.account, self.account2)
        self.assertEqual(income_tx.type, Transaction.Type.INCOME)
        self.assertEqual(income_tx.amount, data['amount_received'])
        self.assertEqual(income_tx.category, self.category1)
        self.assertEqual(income_tx.owner, self.owner)
        self.assertEqual(income_tx.date, data['date'])
        self.assertIn(str(entry.id)[:8], income_tx.description)


    def test_dca_entry_form_save_update_linked_transactions(self):
        # 1. Create an initial DCAEntry with linked transactions
        initial_data = {
            'date': date(2023, 6, 1),
            'amount_paid': Decimal('50.00'),
            'amount_received': Decimal('0.005'),
            'create_transaction': True,
            'from_account': self.account1.pk,
            'to_account': self.account2.pk,
            'from_category': self.category1.pk,
            'to_category': self.category1.pk,
        }
        initial_form = DCAEntryForm(data=initial_data, strategy=self.strategy1, owner=self.owner)
        self.assertTrue(initial_form.is_valid(), initial_form.errors.as_json())
        initial_entry = initial_form.save()

        self.assertIsNotNone(initial_entry.expense_transaction)
        self.assertIsNotNone(initial_entry.income_transaction)

        # 2. Data for updating the form
        update_data = {
            'date': initial_entry.date, # Keep date same or change, as needed
            'amount_paid': Decimal('55.00'), # New value
            'amount_received': Decimal('0.006'), # New value
            # 'create_transaction': False, # Or not present, form should not create new if instance has linked tx
            'from_account': initial_entry.expense_transaction.account.pk, # Keep same accounts
            'to_account': initial_entry.income_transaction.account.pk,
            'from_category': initial_entry.expense_transaction.category.pk,
            'to_category': initial_entry.income_transaction.category.pk,
        }

        # When create_transaction is not checked (or False), it means we are not creating *new* transactions,
        # but if the instance already has linked transactions, they *should* be updated.
        # The form's save method should handle this.

        update_form = DCAEntryForm(data=update_data, instance=initial_entry, strategy=initial_entry.strategy, owner=self.owner)

        if not update_form.is_valid():
            print(update_form.errors.as_json()) # Print errors if form is invalid
        self.assertTrue(update_form.is_valid())

        updated_entry = update_form.save()

        # Refresh from DB to ensure changes are saved and reflected
        updated_entry.refresh_from_db()
        if updated_entry.expense_transaction: # Check if it exists before trying to refresh
            updated_entry.expense_transaction.refresh_from_db()
        if updated_entry.income_transaction: # Check if it exists before trying to refresh
            updated_entry.income_transaction.refresh_from_db()


        self.assertEqual(updated_entry.amount_paid, Decimal('55.00'))
        self.assertEqual(updated_entry.amount_received, Decimal('0.006'))

        self.assertIsNotNone(updated_entry.expense_transaction, "Expense transaction should still be linked.")
        self.assertEqual(updated_entry.expense_transaction.amount, Decimal('55.00'))

        self.assertIsNotNone(updated_entry.income_transaction, "Income transaction should still be linked.")
        self.assertEqual(updated_entry.income_transaction.amount, Decimal('0.006'))
