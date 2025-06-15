import datetime
from decimal import Decimal
from collections import OrderedDict
import json # Added for view tests

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.template.defaultfilters import date as date_filter
from django.urls import reverse # Added for view tests
from dateutil.relativedelta import relativedelta # Added for date calculations

from apps.currencies.models import Currency
from apps.accounts.models import Account, AccountGroup
from apps.transactions.models import Transaction
from apps.net_worth.utils.calculate_net_worth import (
    calculate_historical_currency_net_worth,
    calculate_historical_account_balance,
)
# Mocking get_current_user from thread_local
from apps.common.middleware.thread_local import get_current_user, set_current_user

User = get_user_model()

class BaseNetWorthTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="networthuser@example.com", password="password")
        self.other_user = User.objects.create_user(email="othernetworth@example.com", password="password")

        # Set current user for thread_local middleware
        set_current_user(self.user)

        self.client = Client()
        self.client.login(email="networthuser@example.com", password="password")

        self.currency_usd = Currency.objects.create(code="USD", name="US Dollar", decimal_places=2)
        self.currency_eur = Currency.objects.create(code="EUR", name="Euro", decimal_places=2)

        self.account_group_main = AccountGroup.objects.create(name="Main Group", owner=self.user)

        self.account_usd_1 = Account.objects.create(
            name="USD Account 1", currency=self.currency_usd, owner=self.user, group=self.account_group_main
        )
        self.account_usd_2 = Account.objects.create(
            name="USD Account 2", currency=self.currency_usd, owner=self.user, group=self.account_group_main
        )
        self.account_eur_1 = Account.objects.create(
            name="EUR Account 1", currency=self.currency_eur, owner=self.user, group=self.account_group_main
        )
        # Public account for visibility tests
        self.account_public_usd = Account.objects.create(
            name="Public USD Account", currency=self.currency_usd, visibility=Account.Visibility.PUBLIC
        )

    def tearDown(self):
        # Clear current user
        set_current_user(None)


class CalculateNetWorthUtilsTests(BaseNetWorthTest):
    def test_calculate_historical_currency_net_worth_no_transactions(self):
        qs = Transaction.objects.none()
        result = calculate_historical_currency_net_worth(qs)

        current_month_str = date_filter(timezone.localdate(timezone.now()), "b Y")
        next_month_str = date_filter(timezone.localdate(timezone.now()) + relativedelta(months=1), "b Y")

        self.assertIn(current_month_str, result)
        self.assertIn(next_month_str, result)

        expected_currencies_present = {"US Dollar", "Euro"} # Based on created accounts for self.user
        actual_currencies_in_result = set()
        if result and result[current_month_str]: # Check if current_month_str key exists and has data
            actual_currencies_in_result = set(result[current_month_str].keys())

        self.assertTrue(expected_currencies_present.issubset(actual_currencies_in_result) or not result[current_month_str])


    def test_calculate_historical_currency_net_worth_single_currency(self):
        Transaction.objects.create(account=self.account_usd_1, owner=self.user, type=Transaction.Type.INCOME, amount=Decimal("1000"), date=datetime.date(2023, 10, 5), reference_date=datetime.date(2023,10,1), is_paid=True)
        Transaction.objects.create(account=self.account_usd_1, owner=self.user, type=Transaction.Type.EXPENSE, amount=Decimal("200"), date=datetime.date(2023, 10, 15), reference_date=datetime.date(2023,10,1), is_paid=True)
        Transaction.objects.create(account=self.account_usd_2, owner=self.user, type=Transaction.Type.INCOME, amount=Decimal("300"), date=datetime.date(2023, 11, 5), reference_date=datetime.date(2023,11,1), is_paid=True)

        qs = Transaction.objects.filter(owner=self.user, account__currency=self.currency_usd)
        result = calculate_historical_currency_net_worth(qs)

        oct_str = date_filter(datetime.date(2023, 10, 1), "b Y")
        nov_str = date_filter(datetime.date(2023, 11, 1), "b Y")
        dec_str = date_filter(datetime.date(2023, 12, 1), "b Y")


        self.assertIn(oct_str, result)
        self.assertEqual(result[oct_str]["US Dollar"], Decimal("800.00"))

        self.assertIn(nov_str, result)
        self.assertEqual(result[nov_str]["US Dollar"], Decimal("1100.00"))

        self.assertIn(dec_str, result)
        self.assertEqual(result[dec_str]["US Dollar"], Decimal("1100.00"))


    def test_calculate_historical_currency_net_worth_multi_currency(self):
        Transaction.objects.create(account=self.account_usd_1, owner=self.user, type=Transaction.Type.INCOME, amount=Decimal("1000"), date=datetime.date(2023, 10, 5), reference_date=datetime.date(2023,10,1), is_paid=True)
        Transaction.objects.create(account=self.account_eur_1, owner=self.user, type=Transaction.Type.INCOME, amount=Decimal("500"), date=datetime.date(2023, 10, 10), reference_date=datetime.date(2023,10,1), is_paid=True)
        Transaction.objects.create(account=self.account_usd_1, owner=self.user, type=Transaction.Type.EXPENSE, amount=Decimal("100"), date=datetime.date(2023, 11, 5), reference_date=datetime.date(2023,11,1), is_paid=True)
        Transaction.objects.create(account=self.account_eur_1, owner=self.user, type=Transaction.Type.INCOME, amount=Decimal("50"), date=datetime.date(2023, 11, 15), reference_date=datetime.date(2023,11,1), is_paid=True)

        qs = Transaction.objects.filter(owner=self.user)
        result = calculate_historical_currency_net_worth(qs)

        oct_str = date_filter(datetime.date(2023, 10, 1), "b Y")
        nov_str = date_filter(datetime.date(2023, 11, 1), "b Y")

        self.assertEqual(result[oct_str]["US Dollar"], Decimal("1000.00"))
        self.assertEqual(result[oct_str]["Euro"], Decimal("500.00"))
        self.assertEqual(result[nov_str]["US Dollar"], Decimal("900.00"))
        self.assertEqual(result[nov_str]["Euro"], Decimal("550.00"))

    def test_calculate_historical_currency_net_worth_public_account_visibility(self):
        Transaction.objects.create(account=self.account_usd_1, owner=self.user, type=Transaction.Type.INCOME, amount=Decimal("100"), date=datetime.date(2023,10,1), reference_date=datetime.date(2023,10,1), is_paid=True)
        Transaction.objects.create(account=self.account_public_usd, type=Transaction.Type.INCOME, amount=Decimal("200"), date=datetime.date(2023,10,1), reference_date=datetime.date(2023,10,1), is_paid=True)

        qs = Transaction.objects.filter(Q(owner=self.user) | Q(account__visibility=Account.Visibility.PUBLIC))
        result = calculate_historical_currency_net_worth(qs)
        oct_str = date_filter(datetime.date(2023, 10, 1), "b Y")

        self.assertEqual(result[oct_str]["US Dollar"], Decimal("300.00"))


    def test_calculate_historical_account_balance_no_transactions(self):
        qs = Transaction.objects.none()
        result = calculate_historical_account_balance(qs)
        current_month_str = date_filter(timezone.localdate(timezone.now()), "b Y")
        next_month_str = date_filter(timezone.localdate(timezone.now()) + relativedelta(months=1), "b Y")

        self.assertIn(current_month_str, result)
        self.assertIn(next_month_str, result)
        if result and result[current_month_str]:
            for account_name in [self.account_usd_1.name, self.account_eur_1.name, self.account_public_usd.name]:
                self.assertEqual(result[current_month_str].get(account_name, Decimal(0)), Decimal("0.00"))


    def test_calculate_historical_account_balance_single_account(self):
        Transaction.objects.create(account=self.account_usd_1, owner=self.user, type=Transaction.Type.INCOME, amount=Decimal("1000"), date=datetime.date(2023, 10, 5), reference_date=datetime.date(2023,10,1), is_paid=True)
        Transaction.objects.create(account=self.account_usd_1, owner=self.user, type=Transaction.Type.EXPENSE, amount=Decimal("200"), date=datetime.date(2023, 10, 15), reference_date=datetime.date(2023,10,1), is_paid=True)
        Transaction.objects.create(account=self.account_usd_1, owner=self.user, type=Transaction.Type.INCOME, amount=Decimal("50"), date=datetime.date(2023, 11, 5), reference_date=datetime.date(2023,11,1), is_paid=True)

        qs = Transaction.objects.filter(account=self.account_usd_1)
        result = calculate_historical_account_balance(qs)

        oct_str = date_filter(datetime.date(2023, 10, 1), "b Y")
        nov_str = date_filter(datetime.date(2023, 11, 1), "b Y")

        self.assertEqual(result[oct_str][self.account_usd_1.name], Decimal("800.00"))
        self.assertEqual(result[nov_str][self.account_usd_1.name], Decimal("850.00"))

    def test_calculate_historical_account_balance_multiple_accounts(self):
        Transaction.objects.create(account=self.account_usd_1, owner=self.user, type=Transaction.Type.INCOME, amount=Decimal("100"), date=datetime.date(2023,10,1), reference_date=datetime.date(2023,10,1), is_paid=True)
        Transaction.objects.create(account=self.account_eur_1, owner=self.user, type=Transaction.Type.INCOME, amount=Decimal("200"), date=datetime.date(2023,10,1), reference_date=datetime.date(2023,10,1), is_paid=True)
        Transaction.objects.create(account=self.account_usd_1, owner=self.user, type=Transaction.Type.EXPENSE, amount=Decimal("30"), date=datetime.date(2023,11,1), reference_date=datetime.date(2023,11,1), is_paid=True)

        qs = Transaction.objects.filter(owner=self.user)
        result = calculate_historical_account_balance(qs)
        oct_str = date_filter(datetime.date(2023, 10, 1), "b Y")
        nov_str = date_filter(datetime.date(2023, 11, 1), "b Y")

        self.assertEqual(result[oct_str][self.account_usd_1.name], Decimal("100.00"))
        self.assertEqual(result[oct_str][self.account_eur_1.name], Decimal("200.00"))
        self.assertEqual(result[nov_str][self.account_usd_1.name], Decimal("70.00"))
        self.assertEqual(result[nov_str][self.account_eur_1.name], Decimal("200.00"))


    def test_date_range_handling_in_utils(self):
        qs_empty = Transaction.objects.none()
        today = timezone.localdate(timezone.now())
        start_of_this_month_str = date_filter(today.replace(day=1), "b Y")
        start_of_next_month_str = date_filter((today.replace(day=1) + relativedelta(months=1)), "b Y")

        currency_result = calculate_historical_currency_net_worth(qs_empty)
        self.assertIn(start_of_this_month_str, currency_result)
        self.assertIn(start_of_next_month_str, currency_result)

        account_result = calculate_historical_account_balance(qs_empty)
        self.assertIn(start_of_this_month_str, account_result)
        self.assertIn(start_of_next_month_str, account_result)

    def test_archived_account_exclusion_in_currency_net_worth(self):
        archived_usd_acc = Account.objects.create(
            name="Archived USD", currency=self.currency_usd, owner=self.user, is_archived=True
        )
        Transaction.objects.create(account=self.account_usd_1, owner=self.user, type=Transaction.Type.INCOME, amount=Decimal("100"), date=datetime.date(2023,10,1), reference_date=datetime.date(2023,10,1), is_paid=True)
        Transaction.objects.create(account=archived_usd_acc, owner=self.user, type=Transaction.Type.INCOME, amount=Decimal("500"), date=datetime.date(2023,10,1), reference_date=datetime.date(2023,10,1), is_paid=True)

        qs = Transaction.objects.filter(owner=self.user, account__is_archived=False)
        result = calculate_historical_currency_net_worth(qs)
        oct_str = date_filter(datetime.date(2023, 10, 1), "b Y")

        if oct_str in result:
            self.assertEqual(result[oct_str].get("US Dollar", Decimal(0)), Decimal("100.00"))
        elif result:
            self.fail(f"{oct_str} not found in result, but other data exists.")


    def test_archived_account_exclusion_in_account_balance(self):
        archived_usd_acc = Account.objects.create(
            name="Archived USD Acct Bal", currency=self.currency_usd, owner=self.user, is_archived=True
        )
        Transaction.objects.create(account=self.account_usd_1, owner=self.user, type=Transaction.Type.INCOME, amount=Decimal("100"), date=datetime.date(2023,10,1), reference_date=datetime.date(2023,10,1), is_paid=True)
        Transaction.objects.create(account=archived_usd_acc, owner=self.user, type=Transaction.Type.INCOME, amount=Decimal("500"), date=datetime.date(2023,10,1), reference_date=datetime.date(2023,10,1), is_paid=True)

        qs = Transaction.objects.filter(owner=self.user)
        result = calculate_historical_account_balance(qs)
        oct_str = date_filter(datetime.date(2023, 10, 1), "b Y")

        if oct_str in result:
            self.assertIn(self.account_usd_1.name, result[oct_str])
            self.assertEqual(result[oct_str][self.account_usd_1.name], Decimal("100.00"))
            self.assertNotIn(archived_usd_acc.name, result[oct_str])
        elif result:
             self.fail(f"{oct_str} not found in result for account balance, but other data exists.")


class NetWorthViewTests(BaseNetWorthTest):
    def test_net_worth_current_view(self):
        Transaction.objects.create(account=self.account_usd_1, owner=self.user, type=Transaction.Type.INCOME, amount=Decimal("1200.50"), date=datetime.date(2023, 10, 5), reference_date=datetime.date(2023,10,1), is_paid=True)
        Transaction.objects.create(account=self.account_eur_1, owner=self.user, type=Transaction.Type.INCOME, amount=Decimal("800.75"), date=datetime.date(2023, 10, 10), reference_date=datetime.date(2023,10,1), is_paid=True)
        Transaction.objects.create(account=self.account_usd_2, owner=self.user, type=Transaction.Type.INCOME, amount=Decimal("300.00"), date=datetime.date(2023, 9, 1), reference_date=datetime.date(2023,9,1), is_paid=False) # This is unpaid


        response = self.client.get(reverse("net_worth_current"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "net_worth/net_worth.html")

        # Current net worth display should only include paid transactions
        self.assertContains(response, "US Dollar")
        self.assertContains(response, "1,200.50")
        self.assertContains(response, "Euro")
        self.assertContains(response, "800.75")

        chart_data_currency_json = response.context.get("chart_data_currency_json")
        self.assertIsNotNone(chart_data_currency_json)
        chart_data_currency = json.loads(chart_data_currency_json)
        self.assertIn("labels", chart_data_currency)
        self.assertIn("datasets", chart_data_currency)

        # Historical chart data in net_worth_current view uses a queryset that is NOT filtered by is_paid.
        sep_str = date_filter(datetime.date(2023, 9, 1), "b Y")
        if sep_str in chart_data_currency["labels"]:
            usd_dataset = next((ds for ds in chart_data_currency["datasets"] if ds["label"] == "US Dollar"), None)
            self.assertIsNotNone(usd_dataset)
            sep_idx = chart_data_currency["labels"].index(sep_str)
            # The $300 from Sep (account_usd_2) should be part of the historical calculation for the chart
            self.assertEqual(usd_dataset["data"][sep_idx], 300.00)


    def test_net_worth_projected_view(self):
        Transaction.objects.create(account=self.account_usd_1, owner=self.user, type=Transaction.Type.INCOME, amount=Decimal("1000"), date=datetime.date(2023, 10, 5), reference_date=datetime.date(2023,10,1), is_paid=True)
        Transaction.objects.create(account=self.account_usd_2, owner=self.user, type=Transaction.Type.INCOME, amount=Decimal("500"), date=datetime.date(2023, 11, 1), reference_date=datetime.date(2023,11,1), is_paid=False) # Unpaid

        response = self.client.get(reverse("net_worth_projected"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "net_worth/net_worth.html")

        # `currency_net_worth` in projected view also uses a queryset NOT filtered by is_paid when calling `calculate_currency_totals`.
        self.assertContains(response, "US Dollar")
        self.assertContains(response, "1,500.00") # 1000 (paid) + 500 (unpaid)

        chart_data_currency_json = response.context.get("chart_data_currency_json")
        self.assertIsNotNone(chart_data_currency_json)
        chart_data_currency = json.loads(chart_data_currency_json)
        self.assertIn("labels", chart_data_currency)
        self.assertIn("datasets", chart_data_currency)

        nov_str = date_filter(datetime.date(2023, 11, 1), "b Y")
        oct_str = date_filter(datetime.date(2023, 10, 1), "b Y")

        if nov_str in chart_data_currency["labels"]:
            usd_dataset = next((ds for ds in chart_data_currency["datasets"] if ds["label"] == "US Dollar"), None)
            if usd_dataset:
                nov_idx = chart_data_currency["labels"].index(nov_str)
                # Value in Nov should be cumulative: 1000 (from Oct) + 500 (from Nov unpaid)
                self.assertEqual(usd_dataset["data"][nov_idx], 1500.00)
                # Check October value if it also exists
                if oct_str in chart_data_currency["labels"]:
                    oct_idx = chart_data_currency["labels"].index(oct_str)
                    self.assertEqual(usd_dataset["data"][oct_idx], 1000.00)
