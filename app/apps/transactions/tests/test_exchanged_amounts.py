from datetime import date, datetime, timezone as dt_timezone
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Account, AccountGroup
from apps.common.middleware.thread_local import delete_current_user, write_current_user
from apps.currencies.models import Currency, ExchangeRate
from apps.insights.utils.month_by_month import get_month_by_month_data
from apps.insights.utils.overview import get_grouped_totals
from apps.insights.utils.year_by_year import get_year_by_year_data
from apps.transactions.models import Transaction, TransactionCategory
from apps.transactions.utils.calculations import (
    calculate_account_totals,
    calculate_currency_totals,
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
class ExchangedAmountsTestBase(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="exchanged@test.com", password="testpass123"
        )
        self.client.login(username="exchanged@test.com", password="testpass123")
        write_current_user(self.user)
        self.addCleanup(delete_current_user)

        self.usd = Currency.objects.create(
            code="USD", name="US Dollar", decimal_places=2, prefix="$ "
        )
        self.eur = Currency.objects.create(
            code="EUR",
            name="Euro",
            decimal_places=2,
            prefix="€ ",
            exchange_currency=self.usd,
        )
        ExchangeRate.objects.create(
            from_currency=self.eur,
            to_currency=self.usd,
            rate=Decimal("2"),
            date=datetime(2026, 1, 1, tzinfo=dt_timezone.utc),
        )
        self.account = Account.objects.create(
            name="Euro Account",
            group=AccountGroup.objects.create(name="Group"),
            currency=self.eur,
        )
        self.transaction = Transaction.objects.create(
            account=self.account,
            type=Transaction.Type.INCOME,
            is_paid=True,
            date=date(2026, 3, 10),
            reference_date=date(2026, 3, 1),
            amount=Decimal("100"),
            description="Salary",
            category=TransactionCategory.objects.create(name="Work"),
        )

    def _hide_for(self, obj):
        obj.show_exchanged_amounts = False
        obj.save()


class TransactionExchangedAmountTests(ExchangedAmountsTestBase):
    def test_shown_by_default(self):
        exchanged = self.transaction.displayed_exchanged_amount()

        self.assertEqual(exchanged["amount"], Decimal("200"))
        self.assertEqual(exchanged["prefix"], "$ ")

    def test_currency_can_hide_it(self):
        self._hide_for(self.eur)
        self.transaction.refresh_from_db()

        self.assertIsNone(self.transaction.displayed_exchanged_amount())
        # Only hidden from display, the API keeps returning it
        self.assertEqual(self.transaction.exchanged_amount()["amount"], Decimal("200"))

    def test_account_exchange_currency_follows_the_account_setting(self):
        self.account.exchange_currency = self.usd
        self.account.save()
        self._hide_for(self.eur)
        self.transaction.refresh_from_db()

        self.assertEqual(
            self.transaction.displayed_exchanged_amount()["amount"], Decimal("200")
        )

        self._hide_for(self.account)
        self.transaction.refresh_from_db()

        self.assertIsNone(self.transaction.displayed_exchanged_amount())

    def test_monthly_list_hides_it(self):
        url = reverse("monthly_transactions_list", kwargs={"month": 3, "year": 2026})

        response = self.client.get(url, HTTP_HX_REQUEST="true")
        self.assertContains(response, "exchanged-amount")

        self._hide_for(self.eur)
        response = self.client.get(url, HTTP_HX_REQUEST="true")
        self.assertContains(response, f'data-transaction-id="{self.transaction.id}"')
        self.assertNotContains(response, "exchanged-amount")


class TotalsExchangedAmountTests(ExchangedAmountsTestBase):
    def test_currency_totals_hide_it_but_keep_consolidating(self):
        self._hide_for(self.eur)

        totals = calculate_currency_totals(Transaction.objects.all(), deep_search=True)

        self.assertNotIn("exchanged", totals[self.eur.id])
        self.assertEqual(
            totals[self.usd.id]["consolidated"]["total_final"], Decimal("200")
        )

    def test_currency_totals_hide_it_for_currencies_found_by_deep_search(self):
        brl = Currency.objects.create(code="BRL", name="Real", decimal_places=2)
        self.usd.exchange_currency = brl
        self.usd.save()

        totals = calculate_currency_totals(Transaction.objects.all(), deep_search=True)
        self.assertIn("exchanged", totals[self.usd.id])

        self._hide_for(self.usd)
        totals = calculate_currency_totals(Transaction.objects.all(), deep_search=True)
        self.assertNotIn("exchanged", totals[self.usd.id])

    def test_account_totals_follow_the_account_setting(self):
        self.account.exchange_currency = self.usd
        self.account.save()

        totals = calculate_account_totals(Transaction.objects.all())
        self.assertEqual(
            totals[self.account.id]["exchanged"]["total_final"], Decimal("200")
        )

        self._hide_for(self.account)
        totals = calculate_account_totals(Transaction.objects.all())
        self.assertNotIn("exchanged", totals[self.account.id])

    def test_insights_hide_it(self):
        def exchanged_totals():
            month_data = get_month_by_month_data(year=2026)
            year_data = get_year_by_year_data()
            return [
                month_data["grand_total"]["currencies"][self.eur.id],
                month_data["month_totals"][3]["currencies"][self.eur.id],
                year_data["grand_total"]["currencies"][self.eur.id],
                year_data["year_totals"][2026]["currencies"][self.eur.id],
            ]

        def overview_total():
            overview = get_grouped_totals(Transaction.objects.all(), ["categories"])
            return next(iter(overview.values()))["currencies"][self.eur.id]

        for total in exchanged_totals():
            self.assertEqual(total["exchanged"]["final_total"], Decimal("200"))
        self.assertEqual(overview_total()["exchanged"]["shown"]["total"], Decimal("200"))

        self._hide_for(self.eur)
        for total in exchanged_totals():
            self.assertNotIn("exchanged", total)
        self.assertNotIn("exchanged", overview_total())

    def test_net_worth_keeps_the_consolidated_total(self):
        self._hide_for(self.eur)

        response = self.client.get(reverse("net_worth"), {"view_type": "current"})

        currency_net_worth = response.context["currency_net_worth"]
        self.assertNotIn("exchanged", currency_net_worth[self.eur.id])
        self.assertEqual(
            currency_net_worth[self.usd.id]["consolidated"]["total_final"],
            Decimal("200"),
        )
        self.assertContains(response, "Consolidated")
