import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Account
from apps.common.middleware.thread_local import delete_current_user, write_current_user
from apps.currencies.models import Currency, ExchangeRate
from apps.investments.services import get_holding_performance, summarize
from apps.transactions.models import (
    Transaction,
    TransactionCategory,
    TransactionEntity,
    TransactionTag,
)

D = Decimal
IN, EX = Transaction.Type.INCOME, Transaction.Type.EXPENSE


def tx(account, type_, amount, date, **kwargs):
    return Transaction.objects.create(
        account=account, type=type_, amount=D(amount), date=date, **kwargs
    )


def transfer(from_account, from_amount, to_account, to_amount, date):
    out = tx(from_account, EX, from_amount, date)
    inc = tx(to_account, IN, to_amount, date, linked_transaction=out)
    out.linked_transaction = inc
    out.save()
    return out, inc


class HoldingPerformanceTests(TestCase):
    def setUp(self):
        self.eur = Currency.objects.create(code="EUR", name="Euro", decimal_places=2)
        self.brl = Currency.objects.create(code="BRL", name="Real", decimal_places=2)
        self.vwce = Currency.objects.create(
            code="VWCE.DE", name="VWCE", decimal_places=4, exchange_currency=self.eur
        )
        self.cash = Account.objects.create(name="Cash", currency=self.eur)
        self.etf = Account.objects.create(
            name="VWCE",
            currency=self.vwce,
            exchange_currency=self.eur,
            is_investment=True,
            is_asset=True,
        )
        self.d1 = datetime.date(2026, 1, 10)
        self.d2 = datetime.date(2026, 2, 10)
        self.d3 = datetime.date(2026, 3, 10)

    def rate(self, value, date):
        ExchangeRate.objects.create(
            from_currency=self.vwce,
            to_currency=self.eur,
            rate=D(value),
            date=timezone.make_aware(datetime.datetime.combine(date, datetime.time())),
        )

    def test_priced_average_cost_realized_and_income(self):
        transfer(self.cash, "1000", self.etf, "10", self.d1)
        transfer(self.cash, "1200", self.etf, "10", self.d2)
        transfer(self.etf, "5", self.cash, "700", self.d3)
        self.rate("130", timezone.localdate())

        entity = TransactionEntity.objects.create(name="Vanguard")
        other = TransactionEntity.objects.create(name="Vanguard JCP")
        self.etf.income_entities.set([entity, other])
        dividend = tx(self.cash, IN, "30", self.d3)
        dividend.entities.add(entity, other)  # matches twice, counted once

        perf = get_holding_performance(self.etf)

        self.assertTrue(perf.priced)
        self.assertEqual(perf.quantity, D("15"))
        self.assertEqual(perf.cost_basis, D("1650"))
        self.assertEqual(perf.average_cost, D("110"))
        self.assertEqual(perf.realized, D("150"))  # 700 - 5 * 110
        self.assertEqual(perf.market_value, D("1950"))
        self.assertEqual(perf.unrealized, D("300"))
        self.assertEqual(perf.income, D("30"))
        self.assertEqual(perf.contributed, D("2200"))
        self.assertEqual(perf.withdrawn, D("700"))
        self.assertEqual(perf.total_return, D("480"))
        self.assertFalse(perf.estimated)

    def test_unlinked_inflow_on_priced_account_is_costed_at_market(self):
        self.rate("90", self.d1)
        tx(self.etf, IN, "2", self.d1)

        perf = get_holding_performance(self.etf)

        self.assertEqual(perf.cost_basis, D("180"))
        self.assertTrue(perf.estimated)
        self.assertEqual(perf.contributed, D("0"))

    def test_value_tracked_cdb_with_tax_on_redemption(self):
        cdb = Account.objects.create(
            name="CDB", currency=self.brl, is_investment=True, is_asset=True
        )
        checking = Account.objects.create(name="Checking", currency=self.brl)
        result = TransactionCategory.objects.create(name="Yield")
        cdb.income_categories.set([result])
        transfer(checking, "1000", cdb, "1000", self.d1)
        tx(cdb, IN, "100", self.d2, category=result)  # balance reconciliation
        tx(cdb, EX, "22.50", self.d3, category=result)  # income tax withheld

        perf = get_holding_performance(cdb)
        self.assertFalse(perf.priced)
        self.assertEqual(perf.market_value, D("1077.50"))
        self.assertEqual(perf.cost_basis, D("1000"))
        self.assertEqual(perf.unrealized, D("77.50"))

        transfer(cdb, "1077.50", checking, "1077.50", self.d3)
        perf = get_holding_performance(cdb)
        self.assertEqual(perf.quantity, D("0"))
        self.assertEqual(perf.cost_basis, D("0"))
        self.assertEqual(perf.realized, D("77.50"))
        self.assertEqual(perf.total_return, D("77.50"))

    def test_value_tracked_salary_account_separates_money_from_yield(self):
        account = Account.objects.create(
            name="Salary", currency=self.brl, is_investment=True
        )
        tag = TransactionTag.objects.create(name="Yield")
        account.income_tags.set([tag])
        tx(account, IN, "5000", self.d1)  # salary, from outside
        tx(account, EX, "1000", self.d2)  # rent, not a loss
        tx(account, IN, "40", self.d3).tags.add(tag)  # reconciled balance

        perf = get_holding_performance(account)

        self.assertEqual(perf.contributed, D("5000"))
        self.assertEqual(perf.withdrawn, D("1000"))
        self.assertEqual(perf.market_value, D("4040"))
        self.assertEqual(perf.cost_basis, D("4000"))
        self.assertEqual(perf.total_return, D("40"))
        self.assertFalse(perf.estimated)

    def test_own_entity_is_a_result_but_only_income_counts_elsewhere(self):
        account = Account.objects.create(
            name="Savings", currency=self.brl, is_investment=True
        )
        other = Account.objects.create(name="Other", currency=self.brl)
        bank = TransactionEntity.objects.create(name="Bank")
        account.income_entities.set([bank])
        tx(account, IN, "1000", self.d1)
        tx(account, IN, "10", self.d2).entities.add(bank)
        tx(other, EX, "99", self.d2).entities.add(bank)

        perf = get_holding_performance(account)

        self.assertEqual(perf.total_return, D("10"))
        self.assertEqual(perf.income, D("0"))

    def test_history_has_one_point_per_month_end(self):
        transfer(self.cash, "1000", self.etf, "10", self.d1)
        self.rate("100", self.d1)
        self.rate("120", self.d3)

        perf = get_holding_performance(
            self.etf, as_of=datetime.date(2026, 3, 15), with_history=True
        )

        self.assertEqual(
            [p["date"] for p in perf.history],
            [
                datetime.date(2026, 1, 31),
                datetime.date(2026, 2, 28),
                datetime.date(2026, 3, 15),
            ],
        )
        self.assertEqual(perf.history[-1]["value"], D("1200"))
        self.assertEqual(perf.history[0]["invested"], D("1000"))

    def test_summarize_groups_by_currency(self):
        transfer(self.cash, "1000", self.etf, "10", self.d1)
        self.rate("110", timezone.localdate())
        totals = summarize([get_holding_performance(self.etf)])
        self.assertEqual(len(totals), 1)
        self.assertEqual(totals[0]["market_value"], D("1100"))
        self.assertEqual(totals[0]["total_return"], D("100"))

    def test_xirr_and_money_weighted_return(self):
        from apps.investments.services import money_weighted_return, xirr

        start, year = datetime.date(2025, 1, 1), datetime.date(2026, 1, 1)
        self.assertAlmostEqual(xirr([(start, D(-1000)), (year, D(1100))]), 0.10, places=6)
        self.assertIsNone(xirr([(start, D(-1000))]))

        # A year or more: annualized
        mw = money_weighted_return([(start, D(-1000), "in")], D(1100), year)
        self.assertTrue(mw["annualized"])
        self.assertAlmostEqual(float(mw["percentage"]), 10, places=3)

        # Less than a year: the return over the period, not an inflated annual rate
        half = datetime.date(2025, 7, 2)
        mw = money_weighted_return([(start, D(-1000), "in")], D(1050), half)
        self.assertFalse(mw["annualized"])
        self.assertAlmostEqual(float(mw["percentage"]), 5, places=3)

        # Money added late weighs less: +100 on 1000 held all year beats the
        # simple +100 / 2000 = 5% when the second 1000 only came in at the end
        flows = [(start, D(-1000), "in"), (datetime.date(2025, 12, 31), D(-1000), "in")]
        mw = money_weighted_return(flows, D(2100), year)
        self.assertGreater(float(mw["percentage"]), 9.9)

    def test_home_currency_counts_the_exchange_rate_move(self):
        from apps.investments.services import in_home_currency

        usd = Currency.objects.create(code="USD", name="Dollar", decimal_places=2)
        usd.exchange_currency = self.brl
        usd.save()
        etf = Currency.objects.create(
            code="VT", name="VT", decimal_places=4, exchange_currency=usd
        )
        cash = Account.objects.create(name="USD cash", currency=usd)
        holding = Account.objects.create(
            name="VT", currency=etf, exchange_currency=usd, is_investment=True
        )
        aware = lambda d: timezone.make_aware(datetime.datetime.combine(d, datetime.time()))
        ExchangeRate.objects.create(from_currency=usd, to_currency=self.brl, rate=D("5"), date=aware(self.d1))
        ExchangeRate.objects.create(from_currency=usd, to_currency=self.brl, rate=D("6"), date=aware(timezone.localdate()))
        ExchangeRate.objects.create(from_currency=etf, to_currency=usd, rate=D("100"), date=aware(timezone.localdate()))
        transfer(cash, "1000", holding, "10", self.d1)

        perf = get_holding_performance(holding)
        self.assertEqual(perf.total_return, D("0"))  # flat in dollars

        home = in_home_currency(perf)
        self.assertEqual(home["currency"], self.brl)
        self.assertEqual(home["market_value"], D("6000"))
        self.assertEqual(home["cost_basis"], D("5000"))
        self.assertEqual(home["total_return"], D("1000"))
        self.assertEqual(home["currency_effect"], D("1000"))  # all of it from the dollar

        totals = summarize([perf], convert=True)
        self.assertEqual([t["currency"] for t in totals], [self.brl])
        self.assertEqual(totals[0]["converted_from"], [usd])
        self.assertEqual(totals[0]["breakdown"][0]["currency"], usd)
        self.assertEqual(totals[0]["breakdown"][0]["market_value"], D("1000"))
        # A single-currency total has nothing to break down
        self.assertEqual(summarize([perf])[0]["breakdown"], [])
        # No rate to anything: stays in its own currency
        self.assertEqual(summarize([get_holding_performance(self.etf)], convert=True)[0]["currency"], self.eur)


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
    WHITENOISE_AUTOREFRESH=True,
    DEMO=False,
)
class InvestmentViewTests(TestCase):
    HTMX = {"HTTP_HX_REQUEST": "true"}

    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(email="o@test.com", password="pw")
        self.stranger = User.objects.create_user(email="s@test.com", password="pw")
        brl = Currency.objects.create(code="BRL", name="Real", decimal_places=2)
        self.account = Account.all_objects.create(
            name="CDB", currency=brl, is_investment=True, owner=self.owner
        )

    def test_owner_sees_list_and_detail(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("investments_list"), **self.HTMX)
        self.assertContains(response, "CDB")
        response = self.client.get(
            reverse("investment_detail", args=[self.account.id]), **self.HTMX
        )
        self.assertEqual(response.status_code, 200)

    def test_stranger_cannot_see_detail(self):
        self.client.force_login(self.stranger)
        response = self.client.get(
            reverse("investment_detail_index", args=[self.account.id])
        )
        self.assertEqual(response.status_code, 404)
