from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone # Though specific dates are used, good for general test setup
from decimal import Decimal
from datetime import date

from apps.accounts.models import Account, AccountGroup
from apps.currencies.models import Currency
from apps.transactions.models import TransactionCategory, Transaction
# from apps.calendar_view.utils.calendar import get_transactions_by_day # Not directly testing this util here

class CalendarViewTests(TestCase): # Renamed from CalendarViewTestCase to CalendarViewTests
    def setUp(self):
        self.user = User.objects.create_user(username='testcalendaruser', password='password')
        self.client = Client()
        self.client.login(username='testcalendaruser', password='password')

        self.currency_usd = Currency.objects.create(name="CV USD", code="CVUSD", decimal_places=2, prefix="$CV ")
        self.account_group = AccountGroup.objects.create(name="CV Group", owner=self.user)
        self.account_usd1 = Account.objects.create(
            name="CV Account USD 1",
            currency=self.currency_usd,
            owner=self.user,
            group=self.account_group
        )
        self.category_cv = TransactionCategory.objects.create(
            name="CV Cat",
            owner=self.user,
            type=TransactionCategory.TransactionType.INFO # Using INFO as a generic type
        )

        # Transactions for specific dates
        self.t1 = Transaction.objects.create(
            owner=self.user, account=self.account_usd1, category=self.category_cv,
            date=date(2023, 3, 5), amount=Decimal("10.00"),
            type=Transaction.Type.EXPENSE, is_paid=True, description="March 5th Tx"
        )
        self.t2 = Transaction.objects.create(
            owner=self.user, account=self.account_usd1, category=self.category_cv,
            date=date(2023, 3, 10), amount=Decimal("20.00"),
            type=Transaction.Type.EXPENSE, is_paid=True, description="March 10th Tx"
        )
        self.t3 = Transaction.objects.create(
            owner=self.user, account=self.account_usd1, category=self.category_cv,
            date=date(2023, 4, 5), amount=Decimal("30.00"),
            type=Transaction.Type.EXPENSE, is_paid=True, description="April 5th Tx"
        )

    def test_calendar_list_view_context_data(self):
        # Assumes 'calendar_view:calendar_list' is the correct URL name for the main calendar view
        # The previous test used 'calendar_view:calendar'. I'll assume 'calendar_list' is the new/correct one.
        # If the view that shows the grid is named 'calendar', this should be adjusted.
        # Based on subtask, this is for calendar_list view.
        url = reverse('calendar_view:calendar_list', kwargs={'month': 3, 'year': 2023})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn('dates', response.context)

        dates_context = response.context['dates']

        entry_mar5 = next((d for d in dates_context if d['date'] == date(2023, 3, 5)), None)
        self.assertIsNotNone(entry_mar5, "Date March 5th not found in context.")
        self.assertIn(self.t1, entry_mar5['transactions'], "Transaction t1 not in March 5th transactions.")

        entry_mar10 = next((d for d in dates_context if d['date'] == date(2023, 3, 10)), None)
        self.assertIsNotNone(entry_mar10, "Date March 10th not found in context.")
        self.assertIn(self.t2, entry_mar10['transactions'], "Transaction t2 not in March 10th transactions.")

        for day_data in dates_context:
            self.assertNotIn(self.t3, day_data['transactions'], f"Transaction t3 (April 5th) found in March {day_data['date']} transactions.")

    def test_calendar_transactions_list_view_specific_day(self):
        url = reverse('calendar_view:calendar_transactions_list', kwargs={'day': 5, 'month': 3, 'year': 2023})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn('transactions', response.context)

        transactions_context = response.context['transactions']

        self.assertIn(self.t1, transactions_context, "Transaction t1 (March 5th) not found in context for specific day view.")
        self.assertNotIn(self.t2, transactions_context, "Transaction t2 (March 10th) found in context for March 5th.")
        self.assertNotIn(self.t3, transactions_context, "Transaction t3 (April 5th) found in context for March 5th.")
        self.assertEqual(len(transactions_context), 1)

    def test_calendar_view_authenticated_user_generic_month(self):
        # This is similar to the old test_calendar_view_authenticated_user.
        # It tests general access to the main calendar view (which might be 'calendar_list' or 'calendar')
        # Let's use the 'calendar' name as it was in the old test, assuming it's the main monthly view.
        # If 'calendar_list' is the actual main monthly view, this might be slightly redundant
        # with the setup of test_calendar_list_view_context_data but still good for general access check.
        url = reverse('calendar_view:calendar', args=[2023, 1]) # e.g. Jan 2023
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # Further context checks could be added here if this view has a different structure than 'calendar_list'
        self.assertIn('dates', response.context) # Assuming it also provides 'dates'
        self.assertIn('current_month_date', response.context)
        self.assertEqual(response.context['current_month_date'], date(2023,1,1))
