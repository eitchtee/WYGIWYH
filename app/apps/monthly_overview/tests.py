from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone # Though specific dates are used, good for general test setup
from decimal import Decimal
from datetime import date

from apps.accounts.models import Account, AccountGroup
from apps.currencies.models import Currency
from apps.transactions.models import TransactionCategory, TransactionTag, Transaction

class MonthlyOverviewViewTests(TestCase): # Renamed from MonthlyOverviewTestCase
    def setUp(self):
        self.user = User.objects.create_user(username='testmonthlyuser', password='password')
        self.client = Client()
        self.client.login(username='testmonthlyuser', password='password')

        self.currency_usd = Currency.objects.create(name="MO USD", code="MOUSD", decimal_places=2, prefix="$MO ")
        self.account_group = AccountGroup.objects.create(name="MO Group", owner=self.user)
        self.account_usd1 = Account.objects.create(
            name="MO Account USD 1",
            currency=self.currency_usd,
            owner=self.user,
            group=self.account_group
        )
        self.category_food = TransactionCategory.objects.create(
            name="MO Food",
            owner=self.user,
            type=TransactionCategory.TransactionType.EXPENSE
        )
        self.category_salary = TransactionCategory.objects.create(
            name="MO Salary",
            owner=self.user,
            type=TransactionCategory.TransactionType.INCOME
        )
        self.tag_urgent = TransactionTag.objects.create(name="Urgent", owner=self.user)

        # Transactions for March 2023
        self.t_food1 = Transaction.objects.create(
            owner=self.user, account=self.account_usd1, category=self.category_food,
            date=date(2023, 3, 5), amount=Decimal("50.00"),
            type=Transaction.Type.EXPENSE, description="Groceries March", is_paid=True
        )
        self.t_food1.tags.add(self.tag_urgent)

        self.t_food2 = Transaction.objects.create(
            owner=self.user, account=self.account_usd1, category=self.category_food,
            date=date(2023, 3, 10), amount=Decimal("25.00"),
            type=Transaction.Type.EXPENSE, description="Lunch March", is_paid=True
        )
        self.t_salary1 = Transaction.objects.create(
            owner=self.user, account=self.account_usd1, category=self.category_salary,
            date=date(2023, 3, 1), amount=Decimal("1000.00"),
            type=Transaction.Type.INCOME, description="March Salary", is_paid=True
        )
        # Transaction for April 2023
        self.t_april_food = Transaction.objects.create(
            owner=self.user, account=self.account_usd1, category=self.category_food,
            date=date(2023, 4, 5), amount=Decimal("30.00"),
            type=Transaction.Type.EXPENSE, description="April Groceries", is_paid=True
        )
        # URL for the main overview page for March 2023, used in the adapted test
        self.url_main_overview_march = reverse('monthly_overview:monthly_overview', kwargs={'month': 3, 'year': 2023})


    def test_transactions_list_no_filters(self):
        url = reverse('monthly_overview:monthly_transactions_list', kwargs={'month': 3, 'year': 2023})
        response = self.client.get(url, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        context_txns = response.context['transactions']
        self.assertIn(self.t_food1, context_txns)
        self.assertIn(self.t_food2, context_txns)
        self.assertIn(self.t_salary1, context_txns)
        self.assertNotIn(self.t_april_food, context_txns)
        self.assertEqual(len(context_txns), 3)

    def test_transactions_list_filter_by_description(self):
        url = reverse('monthly_overview:monthly_transactions_list', kwargs={'month': 3, 'year': 2023})
        response = self.client.get(url + "?description=Groceries", HTTP_HX_REQUEST='true') # Filter for "Groceries March"
        self.assertEqual(response.status_code, 200)
        context_txns = response.context['transactions']
        self.assertIn(self.t_food1, context_txns)
        self.assertNotIn(self.t_food2, context_txns)
        self.assertNotIn(self.t_salary1, context_txns)
        self.assertEqual(len(context_txns), 1)

    def test_transactions_list_filter_by_type_income(self):
        url = reverse('monthly_overview:monthly_transactions_list', kwargs={'month': 3, 'year': 2023})
        response = self.client.get(url + "?type=IN", HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        context_txns = response.context['transactions']
        self.assertIn(self.t_salary1, context_txns)
        self.assertEqual(len(context_txns), 1)

    def test_transactions_list_filter_by_tag(self):
        url = reverse('monthly_overview:monthly_transactions_list', kwargs={'month': 3, 'year': 2023})
        response = self.client.get(url + f"?tags={self.tag_urgent.name}", HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        context_txns = response.context['transactions']
        self.assertIn(self.t_food1, context_txns)
        self.assertEqual(len(context_txns), 1)

    def test_transactions_list_filter_by_category(self):
        url = reverse('monthly_overview:monthly_transactions_list', kwargs={'month': 3, 'year': 2023})
        response = self.client.get(url + f"?category={self.category_food.name}", HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        context_txns = response.context['transactions']
        self.assertIn(self.t_food1, context_txns)
        self.assertIn(self.t_food2, context_txns)
        self.assertEqual(len(context_txns), 2)

    def test_transactions_list_ordering_amount_desc(self):
        url = reverse('monthly_overview:monthly_transactions_list', kwargs={'month': 3, 'year': 2023})
        response = self.client.get(url + "?order=-amount", HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        context_txns = list(response.context['transactions'])
        self.assertEqual(context_txns[0], self.t_salary1) # Amount 1000 (INCOME)
        self.assertEqual(context_txns[1], self.t_food1)   # Amount 50 (EXPENSE)
        self.assertEqual(context_txns[2], self.t_food2)   # Amount 25 (EXPENSE)

    def test_monthly_overview_main_view_authenticated_user(self):
        # This test checks general access and basic context for the main monthly overview page.
        response = self.client.get(self.url_main_overview_march)
        self.assertEqual(response.status_code, 200)
        self.assertIn('current_month_date', response.context)
        self.assertEqual(response.context['current_month_date'], date(2023,3,1))
        # Check for other expected context variables if necessary for this main view.
        # For example, if it also lists transactions or summaries directly in its initial context.
        self.assertIn('transactions_by_day', response.context) # Assuming this is part of the main view context as well
        self.assertIn('total_income_current_month', response.context)
        self.assertIn('total_expenses_current_month', response.context)
