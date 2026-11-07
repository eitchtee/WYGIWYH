"""Investment performance, derived from an account's transactions.

Rules (see the account's "Investment" help text):
- A linked transaction (a transfer) moves money in or out. Its other side says
  what was paid or received, which is the cost or the proceeds.
- An unlinked transaction on an account tracked by value is money coming in or
  going out (a salary, a bill), unless it has one of the account's income
  categories, tags or entities: then it is a gain or a loss (a reconciled balance,
  interest, a tax withheld).
- On a unit-priced account an unlinked outflow is a loss, and an unlinked inflow
  (a gift, an opening balance) has no known cost, so it is costed at the market
  price of that day and the result is flagged as estimated.
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
    # Unlinked transactions counted as gains or losses, on accounts tracked by value
    result_ids: set = field(default_factory=set)
    history: list = field(default_factory=list)
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
    if not perf.priced:
        perf.result_ids = _result_ids(account)

    for tx in transactions:
        while month_ends and month_ends[0] < tx.date:
            perf.history.append(_snapshot(perf, account, month_ends.pop(0)))

        # shortcut: only the forward link is read; WYGIWYH transfers link both ways.
        partner = tx.linked_transaction
        if partner and (partner.account_id == account.id or partner.deleted):
            partner = None
        partner_value = (
            _to(partner.amount, partner.account.currency, valuation_currency, tx.date)
            if partner
            else None
        )
        external = not (perf.priced or partner or tx.id in perf.result_ids)

        if tx.type == Transaction.Type.INCOME:
            if external:
                cost = tx.amount
                perf.contributed += cost
            elif partner_value is not None:
                cost = partner_value
                perf.contributed += cost
            elif perf.priced or partner:
                # No known cost: price it at that day's market value
                cost = _to(tx.amount, account.currency, valuation_currency, tx.date)
                perf.estimated = True
                if partner:
                    perf.contributed += cost or ZERO
            else:
                cost = ZERO  # value-tracked: a gain
            if cost:
                perf.flows.append((tx.date, -cost, "in"))
            perf.quantity += tx.amount
            perf.cost_basis += cost or ZERO
        else:
            if perf.quantity > 0:
                removed = perf.cost_basis * min(tx.amount, perf.quantity) / perf.quantity
            else:
                removed = ZERO
            if partner or external:
                proceeds = tx.amount if external else partner_value
                if proceeds is None:
                    proceeds = _to(tx.amount, account.currency, valuation_currency, tx.date) or ZERO
                    perf.estimated = True
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


def xirr(flows):
    """Annual rate r where the dated flows' present value is zero, as a float
    (0.138 = 13.8% a year). None when it can't be solved."""
    if not flows:
        return None
    start = min(flow[0] for flow in flows)
    points = [((flow[0] - start).days / 365, float(flow[1])) for flow in flows]
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
    exaggerates, so it is turned back into the return over the period held."""
    if not flows or market_value is None:
        return None
    rate = xirr(flows + [(as_of, market_value)])
    if rate is None:
        return None
    days = (as_of - min(flow[0] for flow in flows)).days
    if days >= 365:
        return {"percentage": Decimal(str(round(rate * 100, 4))), "annualized": True}
    period = (1 + rate) ** (days / 365) - 1
    return {"percentage": Decimal(str(round(period * 100, 4))), "annualized": False}


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
