from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from decimal import Decimal
from datetime import date
from collections import OrderedDict

from apps.accounts.models import Account, AccountGroup
from apps.currencies.models import Currency
from apps.transactions.models import TransactionCategory, Transaction
from apps.net_worth.utils.calculate_net_worth import calculate_historical_currency_net_worth, calculate_historical_account_balance
from apps.common.middleware.thread_local import set_current_user, get_current_user

class NetWorthUtilsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testnetworthuser', password='password')

        # Clean up current_user after each test
        self.addCleanup(set_current_user, None)

        self.usd = Currency.objects.create(name="US Dollar", code="USD", decimal_places=2, prefix="$")
        self.eur = Currency.objects.create(name="Euro", code="EUR", decimal_places=2, prefix="€")

        self.category = TransactionCategory.objects.create(name="Test Cat", owner=self.user, type=TransactionCategory.TransactionType.INFO)
        self.account_group = AccountGroup.objects.create(name="NetWorth Test Group", owner=self.user)

        self.account_usd1 = Account.objects.create(name="USD Account 1", currency=self.usd, owner=self.user, group=self.account_group)
        self.account_eur1 = Account.objects.create(name="EUR Account 1", currency=self.eur, owner=self.user, group=self.account_group)

        # --- Transactions for Jan 2023 ---
        # USD1: +1000 (Income)
        Transaction.objects.create(
            description="Jan Salary USD1", account=self.account_usd1, category=self.category,
            type=Transaction.Type.INCOME, amount=Decimal('1000.00'), date=date(2023, 1, 10), is_paid=True, owner=self.user
        )
        # USD1: -50 (Expense)
        Transaction.objects.create(
            description="Jan Food USD1", account=self.account_usd1, category=self.category,
            type=Transaction.Type.EXPENSE, amount=Decimal('50.00'), date=date(2023, 1, 15), is_paid=True, owner=self.user
        )
        # EUR1: +500 (Income)
        Transaction.objects.create(
            description="Jan Bonus EUR1", account=self.account_eur1, category=self.category,
            type=Transaction.Type.INCOME, amount=Decimal('500.00'), date=date(2023, 1, 20), is_paid=True, owner=self.user
        )

        # --- Transactions for Feb 2023 ---
        # USD1: +200 (Income)
        Transaction.objects.create(
            description="Feb Salary USD1", account=self.account_usd1, category=self.category,
            type=Transaction.Type.INCOME, amount=Decimal('200.00'), date=date(2023, 2, 5), is_paid=True, owner=self.user
        )
        # EUR1: -100 (Expense)
        Transaction.objects.create(
            description="Feb Rent EUR1", account=self.account_eur1, category=self.category,
            type=Transaction.Type.EXPENSE, amount=Decimal('100.00'), date=date(2023, 2, 12), is_paid=True, owner=self.user
        )
        # EUR1: +50 (Income)
        Transaction.objects.create(
            description="Feb Side Gig EUR1", account=self.account_eur1, category=self.category,
            type=Transaction.Type.INCOME, amount=Decimal('50.00'), date=date(2023, 2, 18), is_paid=True, owner=self.user
        )
        # No transactions in Mar 2023 for this setup

    def test_calculate_historical_currency_net_worth(self):
        # Set current user for the utility function to access
        set_current_user(self.user)

        qs = Transaction.objects.filter(owner=self.user).order_by('date') # Ensure order for consistent processing

        # The function determines start_date from the earliest transaction (Jan 2023)
        # and end_date from the latest transaction (Feb 2023), then extends end_date by one month (Mar 2023).
        result = calculate_historical_currency_net_worth(qs)

        self.assertIsInstance(result, OrderedDict)

        # Expected months: Jan 2023, Feb 2023, Mar 2023
        # The function formats keys as "YYYY-MM-DD" (first day of month)

        expected_keys = [
            date(2023, 1, 1).strftime('%Y-%m-%d'),
            date(2023, 2, 1).strftime('%Y-%m-%d'),
            date(2023, 3, 1).strftime('%Y-%m-%d') # Extended by one month
        ]
        self.assertEqual(list(result.keys()), expected_keys)

        # --- Jan 2023 ---
        # USD1: +1000 - 50 = 950
        # EUR1: +500
        jan_data = result[expected_keys[0]]
        self.assertEqual(jan_data[self.usd.name], Decimal('950.00'))
        self.assertEqual(jan_data[self.eur.name], Decimal('500.00'))

        # --- Feb 2023 ---
        # USD1: 950 (prev) + 200 = 1150
        # EUR1: 500 (prev) - 100 + 50 = 450
        feb_data = result[expected_keys[1]]
        self.assertEqual(feb_data[self.usd.name], Decimal('1150.00'))
        self.assertEqual(feb_data[self.eur.name], Decimal('450.00'))

        # --- Mar 2023 (Carries over from Feb) ---
        # USD1: 1150
        # EUR1: 450
        mar_data = result[expected_keys[2]]
        self.assertEqual(mar_data[self.usd.name], Decimal('1150.00'))
        self.assertEqual(mar_data[self.eur.name], Decimal('450.00'))

        # Ensure no other currencies are present
        for month_data in result.values():
            self.assertEqual(len(month_data), 2) # Only USD and EUR should be present
            self.assertIn(self.usd.name, month_data)
            self.assertIn(self.eur.name, month_data)

    def test_calculate_historical_account_balance(self):
        set_current_user(self.user)

        qs = Transaction.objects.filter(owner=self.user).order_by('date')
        result = calculate_historical_account_balance(qs)

        self.assertIsInstance(result, OrderedDict)

        expected_keys = [
            date(2023, 1, 1).strftime('%Y-%m-%d'),
            date(2023, 2, 1).strftime('%Y-%m-%d'),
            date(2023, 3, 1).strftime('%Y-%m-%d')
        ]
        self.assertEqual(list(result.keys()), expected_keys)

        # Jan 2023 data
        jan_data = result[expected_keys[0]]
        self.assertEqual(jan_data.get(self.account_usd1.name), Decimal('950.00'))
        self.assertEqual(jan_data.get(self.account_eur1.name), Decimal('500.00'))
        # Ensure only these two accounts are present, as per setUp
        self.assertEqual(len(jan_data), 2)
        self.assertIn(self.account_usd1.name, jan_data)
        self.assertIn(self.account_eur1.name, jan_data)


        # Feb 2023 data
        feb_data = result[expected_keys[1]]
        self.assertEqual(feb_data.get(self.account_usd1.name), Decimal('1150.00'))
        self.assertEqual(feb_data.get(self.account_eur1.name), Decimal('450.00'))
        self.assertEqual(len(feb_data), 2)
        self.assertIn(self.account_usd1.name, feb_data)
        self.assertIn(self.account_eur1.name, feb_data)

        # Mar 2023 data (carried over)
        mar_data = result[expected_keys[2]]
        self.assertEqual(mar_data.get(self.account_usd1.name), Decimal('1150.00'))
        self.assertEqual(mar_data.get(self.account_eur1.name), Decimal('450.00'))
        self.assertEqual(len(mar_data), 2)
        self.assertIn(self.account_usd1.name, mar_data)
        self.assertIn(self.account_eur1.name, mar_data)
