from datetime import date, datetime, timezone as dt_timezone
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.models import Account
from apps.common.middleware.thread_local import delete_current_user, write_current_user
from apps.currencies.models import Currency, ExchangeRate
from apps.transactions.models import Transaction
from apps.transactions.utils.calculations import (
    calculate_consolidated_shares,
    calculate_currency_totals,
)


def component(name, total_final):
    return {"currency": {"name": name}, "total_final": Decimal(total_final)}


class CalculateConsolidatedSharesTests(TestCase):
    def test_shares_add_up_to_the_total(self):
        shares = calculate_consolidated_shares(
            [component("USD", "150"), component("EUR", "50")], Decimal("200")
        )

        self.assertEqual(
            [(share["currency"]["name"], share["share"]) for share in shares],
            [("USD", Decimal("75")), ("EUR", Decimal("25"))],
        )

    def test_sorted_from_largest_to_smallest(self):
        shares = calculate_consolidated_shares(
            [component("USD", "10"), component("BTC", "-5"), component("EUR", "20")],
            Decimal("25"),
        )

        self.assertEqual(
            [share["currency"]["name"] for share in shares], ["EUR", "USD", "BTC"]
        )

    def test_component_that_takes_from_the_total_has_a_negative_share(self):
        shares = calculate_consolidated_shares(
            [component("USD", "300"), component("EUR", "-100")], Decimal("200")
        )

        self.assertEqual(
            [share["share"] for share in shares], [Decimal("150"), Decimal("-50")]
        )

    def test_sign_follows_the_component_when_the_total_is_negative(self):
        shares = calculate_consolidated_shares(
            [component("USD", "100"), component("EUR", "-300")], Decimal("-200")
        )

        self.assertEqual(
            [share["share"] for share in shares], [Decimal("50"), Decimal("-150")]
        )

    def test_components_that_add_nothing_are_left_out(self):
        shares = calculate_consolidated_shares(
            [component("USD", "0"), component("EUR", "50")], Decimal("50")
        )

        self.assertEqual([share["currency"]["name"] for share in shares], ["EUR"])
        self.assertEqual(shares[0]["share"], Decimal("100"))

    def test_no_share_without_a_total(self):
        shares = calculate_consolidated_shares(
            [component("USD", "100"), component("EUR", "-100")], Decimal("0")
        )

        self.assertEqual([share["share"] for share in shares], [None, None])


class CurrencyTotalsConsolidatedComponentsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="shares@test.com", password="testpass123"
        )
        write_current_user(self.user)
        self.addCleanup(delete_current_user)

        self.usd = Currency.objects.create(
            code="USD", name="US Dollar", decimal_places=2, prefix="$ "
        )
        self.eur = Currency.objects.create(
            code="EUR", name="Euro", decimal_places=2, exchange_currency=self.usd
        )
        self.gbp = Currency.objects.create(
            code="GBP", name="Pound", decimal_places=2, exchange_currency=self.usd
        )
        for currency in (self.eur, self.gbp):
            ExchangeRate.objects.create(
                from_currency=currency,
                to_currency=self.usd,
                rate=Decimal("2"),
                date=datetime(2026, 1, 1, tzinfo=dt_timezone.utc),
            )

        self._add(self.usd, Transaction.Type.INCOME, "150")
        self._add(self.eur, Transaction.Type.INCOME, "50")
        self._add(self.gbp, Transaction.Type.EXPENSE, "25")

    def _add(self, currency, transaction_type, amount):
        Transaction.objects.create(
            account=Account.objects.create(
                name=f"{currency.code} account", currency=currency
            ),
            type=transaction_type,
            is_paid=True,
            date=date(2026, 3, 10),
            reference_date=date(2026, 3, 1),
            amount=Decimal(amount),
        )

    def _components(self, totals, currency):
        return [
            (part["currency"]["name"], part["total_final"], part["share"])
            for part in totals[currency.id]["consolidated"]["components"]
        ]

    def test_components_are_in_the_consolidated_currency(self):
        totals = calculate_currency_totals(Transaction.objects.all(), deep_search=True)

        self.assertEqual(
            totals[self.usd.id]["consolidated"]["total_final"], Decimal("200")
        )
        self.assertEqual(
            self._components(totals, self.usd),
            [
                ("US Dollar", Decimal("150"), Decimal("75")),
                ("Euro", Decimal("100"), Decimal("50")),
                ("Pound", Decimal("-50"), Decimal("-25")),
            ],
        )

    def test_currency_without_sources_is_its_only_component(self):
        totals = calculate_currency_totals(Transaction.objects.all(), deep_search=True)

        self.assertEqual(
            self._components(totals, self.eur),
            [("Euro", Decimal("50"), Decimal("100"))],
        )

    def test_hidden_exchanged_amounts_still_count(self):
        self.eur.show_exchanged_amounts = False
        self.eur.save()

        totals = calculate_currency_totals(Transaction.objects.all(), deep_search=True)

        self.assertNotIn("exchanged", totals[self.eur.id])
        self.assertIn(
            ("Euro", Decimal("100"), Decimal("50")),
            self._components(totals, self.usd),
        )

    def test_target_found_by_deep_search(self):
        Transaction.objects.filter(account__currency=self.usd).delete()

        totals = calculate_currency_totals(Transaction.objects.all(), deep_search=True)

        self.assertEqual(
            self._components(totals, self.usd),
            [
                ("Euro", Decimal("100"), Decimal("200")),
                ("Pound", Decimal("-50"), Decimal("-100")),
            ],
        )
