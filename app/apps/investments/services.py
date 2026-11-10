"""Investment performance, derived from an account's transactions.

Rules (see the account's "Investment" help text):
- A linked transaction (a transfer) moves money in or out. On a unit-priced
  account its other side says what was paid or received, which is the cost or
  the proceeds. On an account tracked by value its own amount is.
- An unlinked transaction is money coming in or going out (a salary, a bill, a
  gift), unless it has one of the account's income categories, tags or entities:
  then it is a gain or a loss (a reconciled balance, interest, a tax withheld).
- On a unit-priced account, money that moves without a known other side is
  valued at the market price of that day and the result is flagged as estimated.
- Cost is tracked with the average cost method.
"""

import datetime
from dataclasses import dataclass, field
from decimal import Decimal
from functools import cached_property

from django.db.models import Q
from django.utils import timezone

from apps.currencies.models import ExchangeRate
from apps.currencies.utils.convert import convert, get_exchange_rate
from apps.transactions.models import Transaction

ZERO = Decimal("0")


@dataclass
class HoldingPerformance:
    account: object
    currency: object  # valuation currency
    priced: bool  # True: units x price. False: tracked by value.
    quantity: Decimal = ZERO
    cost_basis: Decimal = ZERO
    price: Decimal | None = None
    price_date: datetime.datetime | None = None
    realized: Decimal = ZERO
    income: Decimal = ZERO
    contributed: Decimal = ZERO
    withdrawn: Decimal = ZERO
    estimated: bool = False
    # Unlinked transactions counted as gains or losses
    result_ids: set = field(default_factory=set)
    history: list = field(default_factory=list)
    # (date, "buy" or "sell", unit price) for linked trades on unit-priced accounts
    trades: list = field(default_factory=list)
    # (date, signed amount) for the gains and losses of an account tracked by value
    results: list = field(default_factory=list)
    # (date, amount, kind) in the valuation currency: negative = money in ("in"),
    # positive = money out ("out" sales/withdrawals, "income"). Used for
    # money-weighted returns and currency conversion.
    flows: list = field(default_factory=list)
    as_of: datetime.date | None = None

    @cached_property
    def money_weighted(self):
        return money_weighted_return(self.flows, self.market_value, self.as_of)

    @property
    def average_cost(self):
        return self.cost_basis / self.quantity if self.quantity else None

    @property
    def market_value(self):
        if self.price is None:
            return None
        return self.quantity * self.price

    @property
    def unrealized(self):
        value = self.market_value
        return None if value is None else value - self.cost_basis

    @property
    def total_return(self):
        return (self.unrealized or ZERO) + self.realized + self.income

    @property
    def return_percentage(self):
        if not self.contributed:
            return None
        return self.total_return / self.contributed * 100

    @property
    def unrealized_percentage(self):
        if not self.cost_basis or self.unrealized is None:
            return None
        return self.unrealized / self.cost_basis * 100


def _to(amount, from_currency, to_currency, date):
    if from_currency == to_currency or not amount:
        return amount
    return convert(amount, from_currency, to_currency, date)[0]


def _price(account, valuation_currency, date):
    if account.currency == valuation_currency:
        return Decimal("1"), None
    rate = get_exchange_rate(account.currency, valuation_currency, date)
    if rate is None:
        return None, None
    return rate.effective_rate, rate.date


def _linked_ids(account, field_name):
    # The join table, not the related manager: that one is per-user and comes back
    # empty without a current user
    relation = account._meta.get_field(field_name)
    return list(
        relation.remote_field.through.objects.filter(account=account).values_list(
            relation.m2m_reverse_name(), flat=True
        )
    )


def income_entity_ids(account):
    return _linked_ids(account, "income_entities")


def _result_ids(account):
    return set(
        Transaction.objects.filter(account=account)
        .filter(
            Q(category__in=_linked_ids(account, "income_categories"))
            | Q(tags__in=_linked_ids(account, "income_tags"))
            | Q(entities__in=income_entity_ids(account))
        )
        .values_list("id", flat=True)
    )


def get_holding_performance(account, as_of=None, with_history=False):
    """Performance of an investment account up to ``as_of`` (today by default),
    in the account's exchange currency, or its own currency if it has none."""
    today = timezone.localdate()
    as_of = as_of or today
    valuation_currency = account.exchange_currency or account.currency
    perf = HoldingPerformance(
        account=account,
        currency=valuation_currency,
        priced=account.exchange_currency_id is not None,
    )

    transactions = (
        Transaction.objects.filter(account=account, is_paid=True, date__lte=as_of)
        .select_related("linked_transaction__account__currency")
        .order_by("date", "id")
    )

    month_ends = _month_ends(transactions, as_of) if with_history else []
    perf.result_ids = _result_ids(account)

    for tx in transactions:
        while month_ends and month_ends[0] < tx.date:
            perf.history.append(_snapshot(perf, account, month_ends.pop(0)))

        # shortcut: only the forward link is read; WYGIWYH transfers link both ways.
        partner = tx.linked_transaction
        if partner and (partner.account_id == account.id or partner.deleted):
            partner = None
        # Money in or out, as opposed to a gain or a loss
        moved = partner or tx.id not in perf.result_ids
        partner_value = None
        if perf.priced and partner:
            partner_value = _to(
                partner.amount, partner.account.currency, valuation_currency, tx.date
            )
        if partner_value is not None:
            value, estimated = partner_value, False
        elif perf.priced:
            # No known other side: that day's market value
            value = _to(tx.amount, account.currency, valuation_currency, tx.date)
            estimated = True
        else:
            value, estimated = tx.amount, False

        if perf.priced and partner_value is not None and tx.amount:
            kind = "buy" if tx.type == Transaction.Type.INCOME else "sell"
            perf.trades.append((tx.date, kind, partner_value / tx.amount))
        elif not (perf.priced or moved):
            sign = 1 if tx.type == Transaction.Type.INCOME else -1
            perf.results.append((tx.date, sign * tx.amount))

        if tx.type == Transaction.Type.INCOME:
            cost = ZERO  # a gain
            if moved:
                cost = value
                perf.contributed += cost or ZERO
                perf.estimated |= estimated
            if cost:
                perf.flows.append((tx.date, -cost, "in"))
            perf.quantity += tx.amount
            perf.cost_basis += cost or ZERO
        else:
            if perf.quantity > 0:
                removed = perf.cost_basis * min(tx.amount, perf.quantity) / perf.quantity
            else:
                removed = ZERO
            if moved:
                proceeds = value or ZERO
                perf.estimated |= estimated
                perf.realized += proceeds - removed
                perf.withdrawn += proceeds
                perf.flows.append((tx.date, proceeds, "out"))
                perf.cost_basis -= removed
            # otherwise a loss, tax or fee: cost stays, so value drops
            perf.quantity -= tx.amount
            if perf.quantity <= 0 and perf.cost_basis:
                perf.realized -= perf.cost_basis
                perf.cost_basis = ZERO

    for month_end in month_ends:
        perf.history.append(_snapshot(perf, account, month_end))

    perf.price, perf.price_date = _price(
        account,
        valuation_currency,
        timezone.now() if as_of == today else as_of,
    )

    entity_ids = income_entity_ids(account)
    if entity_ids:
        income = Transaction.objects.filter(
            entities__in=entity_ids,
            type=Transaction.Type.INCOME,
            is_paid=True,
            date__lte=as_of,
        ).exclude(account=account).distinct().select_related("account__currency")
        for tx in income:
            amount = _to(tx.amount, tx.account.currency, valuation_currency, tx.date)
            if amount:
                perf.income += amount
                perf.flows.append((tx.date, amount, "income"))

    perf.as_of = as_of
    return perf


def xirr(flows, period_days=365):
    """Rate r per ``period_days`` (a year by default) where the dated flows'
    present value is zero, as a float (0.138 = 13.8% a period). None when it
    can't be solved."""
    if not flows:
        return None
    start = min(flow[0] for flow in flows)
    points = [((flow[0] - start).days / period_days, float(flow[1])) for flow in flows]
    if not (any(a < 0 for _, a in points) and any(a > 0 for _, a in points)):
        return None

    def npv(rate):
        return sum(a / (1 + rate) ** t for t, a in points)

    # Bisection: slower than Newton but can't diverge on odd cash flows
    low, high = -0.9999, 100.0
    npv_low = npv(low)
    if npv_low * npv(high) > 0:
        return None
    for _ in range(200):
        mid = (low + high) / 2
        npv_mid = npv(mid)
        if npv_low * npv_mid <= 0:
            high = mid
        else:
            low, npv_low = mid, npv_mid
    return (low + high) / 2


def money_weighted_return(flows, market_value, as_of):
    """Return that accounts for when money went in and out, as
    ``{"percentage": Decimal, "annualized": bool}`` or None.

    Over a year or more it is annualized (XIRR). Below a year an annual rate
    exaggerates, so the rate is solved over the period held instead: annualizing
    a few days blows past what xirr can solve (+1.3% in one day is ~10,600% a year)."""
    if not flows or market_value is None:
        return None
    days = (as_of - min(flow[0] for flow in flows)).days
    annualized = days >= 365
    rate = xirr(flows + [(as_of, market_value)], 365 if annualized else max(days, 1))
    if rate is None:
        return None
    return {"percentage": Decimal(str(round(rate * 100, 4))), "annualized": annualized}


def _month_ends(transactions, as_of):
    first = transactions.values_list("date", flat=True).first()
    if not first:
        return []
    ends = []
    year, month = first.year, first.month
    while True:
        next_first = datetime.date(year + month // 12, month % 12 + 1, 1)
        end = next_first - datetime.timedelta(days=1)
        if end >= as_of:
            ends.append(as_of)
            return ends
        ends.append(end)
        year, month = next_first.year, next_first.month


def _snapshot(perf, account, date):
    price, _ = _price(account, perf.currency, date)
    return {
        "date": date,
        "invested": perf.cost_basis,
        "value": perf.quantity * price if price is not None else None,
        "price": price,
        "average_cost": perf.average_cost,
    }


def conversion_path(currency):
    """``currency`` followed by its exchange currencies (USD -> BRL -> ...), for as
    long as an exchange rate between each step exists."""
    path = [currency]
    while True:
        target = path[-1].exchange_currency
        if (
            target is None
            or target in path
            or get_exchange_rate(path[-1], target, timezone.now()) is None
        ):
            return path
        path.append(target)


def _along(amount, path, date):
    for from_currency, to_currency in zip(path, path[1:]):
        amount = _to(amount, from_currency, to_currency, date)
    return amount


def _native(perf):
    return {
        "currency": perf.currency,
        "market_value": perf.market_value,
        "cost_basis": perf.cost_basis,
        "income": perf.income,
        "total_return": perf.total_return,
        "currency_effect": ZERO,
        "flows": perf.flows,
    }


def in_home_currency(perf):
    """The holding converted along its currency's exchange chain, each cash flow
    at its own date's rate, so currency moves count towards the return.
    None when its currency converts to nothing."""
    path = conversion_path(perf.currency)
    if len(path) == 1:
        return None
    flows = [(d, _along(a, path, d), kind) for d, a, kind in perf.flows]
    value = None
    if perf.market_value is not None:
        value = _along(perf.market_value, path, perf.as_of)
    total_return = (value or ZERO) + sum((a for _, a, _ in flows), ZERO)

    put_in = -sum((a for _, a, k in flows if k == "in"), ZERO)
    put_in_native = -sum((a for _, a, k in perf.flows if k == "in"), ZERO)
    # shortcut: what you still hold is valued at the average rate you paid in,
    # not lot by lot; exact for buy-and-hold, approximate after partial sales.
    cost_basis = (
        perf.cost_basis * put_in / put_in_native
        if put_in_native
        else _along(perf.cost_basis, path, perf.as_of)
    )
    return {
        "currency": path[-1],
        "path": path,
        "market_value": value,
        "cost_basis": cost_basis,
        "income": sum((a for _, a, k in flows if k == "income"), ZERO),
        "total_return": total_return,
        # what the return gained or lost from the exchange rate moving
        "currency_effect": total_return
        - _along(perf.total_return, path, perf.as_of),
        # With a single rate every date converts the same, so the effect reads 0
        "has_rate_history": all(
            ExchangeRate.objects.filter(
                Q(from_currency=a, to_currency=b) | Q(from_currency=b, to_currency=a)
            )[:2].count()
            > 1
            for a, b in zip(path, path[1:])
        ),
        "flows": flows,
        "money_weighted": money_weighted_return(flows, value, perf.as_of),
    }


def summarize(performances, convert=False):
    """Totals per currency. With ``convert``, holdings are first converted along
    their exchange chain (see in_home_currency); the ones that can't be stay in
    their own currency."""
    totals = {}
    for perf in performances:
        figures = (convert and in_home_currency(perf)) or _native(perf)
        total = totals.setdefault(
            figures["currency"].id,
            {
                "currency": figures["currency"],
                "market_value": ZERO,
                "cost_basis": ZERO,
                "total_return": ZERO,
                "income": ZERO,
                "currency_effect": ZERO,
                "converted_from": [],
                "has_rate_history": True,
                "flows": [],
                "as_of": perf.as_of,
                "holdings": [],
            },
        )
        total["holdings"].append(perf)
        for key in ("cost_basis", "total_return", "income", "currency_effect"):
            total[key] += figures[key]
        total["has_rate_history"] &= figures.get("has_rate_history", True)
        if figures["currency"] != perf.currency and perf.currency not in total["converted_from"]:
            total["converted_from"].append(perf.currency)
        # A holding without a price has no end value, so its flows would skew the rate
        if figures["market_value"] is not None:
            total["market_value"] += figures["market_value"]
            total["flows"] += figures["flows"]
    for total in totals.values():
        total["money_weighted"] = money_weighted_return(
            total["flows"], total["market_value"], total["as_of"]
        )
        # The same holdings in their own currencies, for a converted total
        total["breakdown"] = (
            sorted(
                summarize(total["holdings"]),
                key=lambda part: part["currency"] != total["currency"],
            )
            if total["converted_from"]
            else []
        )
    return list(totals.values())


def portfolio_charts(performances):
    """Chart data per total currency (as in summarize with ``convert``): value by
    asset class and by currency, return by investment, and value against invested
    at each month end. Classes are InvestmentClass objects, None for holdings
    without one. Unpriced holdings are left out of the value figures."""
    charts = {}
    for perf in performances:
        figures = in_home_currency(perf) or _native(perf)
        path = figures.get("path", [perf.currency])
        chart = charts.setdefault(
            figures["currency"].id,
            {
                "currency": figures["currency"],
                "classes": {},
                "currencies": {},
                "returns": [],
                "history": {},
            },
        )
        value = figures["market_value"]
        if value:
            key = perf.account.investment_class
            chart["classes"][key] = chart["classes"].get(key, ZERO) + value
            name = perf.currency.name
            chart["currencies"][name] = chart["currencies"].get(name, ZERO) + value
        chart["returns"].append((perf.account.name, figures["total_return"]))
        # shortcut: one rate lookup per holding, month and hop; cache rates per
        # date if portfolios with long histories make this tab slow.
        for point in perf.history:
            totals = chart["history"].setdefault(point["date"], [ZERO, ZERO])
            for i, amount in enumerate((point["value"], point["invested"])):
                if amount is not None:
                    totals[i] += _along(amount, path, point["date"]) or ZERO
    for chart in charts.values():
        for key in ("classes", "currencies"):
            chart[key] = sorted(chart[key].items(), key=lambda item: -item[1])
        chart["returns"].sort(key=lambda item: -item[1])
        chart["history"] = sorted(chart["history"].items())
    return list(charts.values())


def drift_limit(target):
    """How far a class may drift from its target, in percentage points: the
    common 5/25 rule, 5 points or a quarter of the target, whichever is less."""
    return min(Decimal(5), target / 4)


def rebalance(classes, targeted):
    """What to buy or sell so the classes in ``targeted`` (InvestmentClass with a
    target) match their targets, given ``classes`` as (class, value) from
    portfolio_charts. Holdings without a class or target are left out and their
    value is returned as ``left_out``. ``move`` is positive to buy."""
    values = dict(classes)
    total = sum((values.get(cls, ZERO) for cls in targeted), ZERO)
    rows = []
    for cls in targeted:
        value = values.get(cls, ZERO)
        share = value / total * 100 if total else ZERO
        move = total * cls.target / 100 - value
        rows.append(
            {
                "class": cls,
                "value": value,
                "share": share,
                "target": cls.target,
                "move": move,
                "off": abs(share - cls.target) > drift_limit(cls.target),
            }
        )
    left_out = sum(values.values(), ZERO) - total
    return {"total": total, "rows": rows, "left_out": left_out}
