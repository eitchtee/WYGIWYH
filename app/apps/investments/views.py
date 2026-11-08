from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils.formats import date_format
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from apps.accounts.forms import InvestmentClassForm
from apps.accounts.models import Account, InvestmentClass
from apps.common.decorators.htmx import only_htmx
from apps.common.functions.format import get_format
from apps.common.functions.permissions import READ, get_shared_object_or_error
from apps.investments.services import (
    ZERO,
    get_holding_performance,
    in_home_currency,
    income_entity_ids,
    portfolio_charts,
    rebalance,
    summarize,
)
from apps.transactions.models import Transaction


def _holdings():
    return Account.objects.filter(is_investment=True, is_archived=False).select_related(
        "group", "currency", "exchange_currency"
    )


@login_required
def investments_index(request):
    return render(request, "investments/pages/index.html")


@only_htmx
@login_required
def investments_list(request):
    performances = [get_holding_performance(account) for account in _holdings()]

    groups = {}
    for perf in performances:
        group = perf.account.group
        groups.setdefault(group.id if group else None, (group, []))[1].append(perf)

    return render(
        request,
        "investments/fragments/list.html",
        {
            "groups": [
                {"group": group, "holdings": items, "totals": summarize(items)}
                for group, items in sorted(
                    groups.values(), key=lambda g: (g[0] is None, g[0] and g[0].name)
                )
            ],
            "totals": summarize(performances, convert=True),
        },
    )


def _money(currency):
    """What chartMoney (charts.js) needs to format amounts like the rest of the app."""
    return {
        "prefix": currency.prefix,
        "suffix": currency.suffix,
        "decimals": currency.decimal_places,
        "decimal": get_format("DECIMAL_SEPARATOR"),
        "thousand": get_format("THOUSAND_SEPARATOR"),
    }


def _number(amount):
    return None if amount is None else float(amount)


def _per_month(history, entries):
    """Sums (date, amount) entries into the months of ``history``, zero when empty."""
    sums = {(p["date"].year, p["date"].month): ZERO for p in history}
    for date, amount in entries:
        if (date.year, date.month) in sums:
            sums[(date.year, date.month)] += amount
    return [float(amount) for amount in sums.values()]


def _trades_per_month(history, trades, kind):
    """The last trade price of each month, None in months without one."""
    prices = {(p["date"].year, p["date"].month): None for p in history}
    for date, trade_kind, price in trades:
        if trade_kind == kind and (date.year, date.month) in prices:
            prices[(date.year, date.month)] = float(price)
    return list(prices.values())


# Categorical slots in fixed order; past the last one, the rest fold into "Other"
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6"]
OTHER_COLOR = "#898781"


def _shares(items):
    colors = PALETTE[: len(items)]
    if len(items) > len(PALETTE):
        rest = sum(amount for _name, amount in items[len(PALETTE) - 1 :])
        items = items[: len(PALETTE) - 1] + [(_("Other"), rest)]
        colors = PALETTE[:-1] + [OTHER_COLOR]
    total = sum(amount for _name, amount in items)
    return [
        {
            "key": name,
            "name": str(name),
            "amount": amount,
            "share": amount / total * 100 if total else 0,
            "color": color,
        }
        for (name, amount), color in zip(items, colors)
    ]


@only_htmx
@login_required
def investments_charts(request):
    performances = [
        get_holding_performance(account, with_history=True) for account in _holdings()
    ]
    charts = portfolio_charts(performances)
    targeted = _targeted()
    # Shares only mean something against targets that add up to 100%
    if sum(cls.target for cls in targeted) != 100:
        targeted = []
    for i, chart in enumerate(charts):
        chart["data_id"] = f"investment-charts-{i}"
        chart["returns_height"] = max(128, 32 * len(chart["returns"]))
        plan = {row["class"]: row for row in rebalance(chart["classes"], targeted)["rows"]}
        chart["classes"] = _shares(
            [(cls or _("Unclassified"), amount) for cls, amount in chart["classes"]]
        )
        for share in chart["classes"]:
            share["plan"] = plan.get(share["key"])
        chart["currencies"] = _shares(chart["currencies"])
        chart["data"] = {
            "currency": _money(chart["currency"]),
            "classes": [[s["name"], float(s["amount"]), s["color"]] for s in chart["classes"]],
            "currencies": [[s["name"], float(s["amount"]), s["color"]] for s in chart["currencies"]],
            "returns": [[name, float(amount)] for name, amount in chart["returns"]],
            "history": {
                "labels": [date_format(d, "M Y") for d, _t in chart["history"]],
                "value": [float(t[0]) for _d, t in chart["history"]],
                "invested": [float(t[1]) for _d, t in chart["history"]],
            },
        }
    return render(request, "investments/fragments/charts.html", {"charts": charts})


def _targeted():
    return list(InvestmentClass.objects.filter(target__isnull=False))


@only_htmx
@login_required
def investments_rebalance(request):
    targeted = _targeted()
    total_target = sum(cls.target for cls in targeted)
    plans = []
    for chart in portfolio_charts([get_holding_performance(a) for a in _holdings()]):
        plan = rebalance(chart["classes"], targeted)
        plan["currency"] = chart["currency"]
        for row in plan["rows"]:
            # Fractions of a cent shouldn't show as "Buy 0.00"
            row["move"] = round(row["move"], chart["currency"].decimal_places)
            row["size"] = abs(row["move"])
        plans.append(plan)
    return render(
        request,
        "investments/fragments/rebalance.html",
        {"plans": plans, "total_target": total_target, "targeted": targeted},
    )


@login_required
def investment_detail_index(request, account_id):
    account = get_shared_object_or_error(
        Account, request, id=account_id, level=READ, is_investment=True
    )
    return render(request, "investments/pages/detail.html", {"account": account})


@only_htmx
@login_required
def investment_detail(request, account_id):
    account = get_shared_object_or_error(
        Account, request, id=account_id, level=READ, is_investment=True
    )
    perf = get_holding_performance(account, with_history=True)
    transactions = (
        Transaction.objects.filter(account=account)
        .select_related("linked_transaction__account__currency", "category")
        .order_by("-date", "-id")[:50]
    )
    income = []
    entity_ids = income_entity_ids(account)
    if entity_ids:
        income = (
            Transaction.objects.filter(
                entities__in=entity_ids, type=Transaction.Type.INCOME
            )
            .exclude(account=account)
            .distinct()
            .select_related("account__currency")
            .order_by("-date", "-id")[:20]
        )

    history = perf.history
    income_flows = [(d, amount) for d, amount, kind in perf.flows if kind == "income"]
    chart = {
        "currency": _money(perf.currency),
        "labels": [date_format(p["date"], "M Y") for p in history],
        "value": [_number(p["value"]) for p in history],
        "invested": [float(p["invested"]) for p in history],
        "price": [_number(p["price"]) for p in history] if perf.priced else None,
        "average_cost": [_number(p["average_cost"]) for p in history],
        "buys": _trades_per_month(history, perf.trades, "buy"),
        "sells": _trades_per_month(history, perf.trades, "sell"),
        "earnings": _per_month(history, perf.results) if perf.results else None,
        "income": _per_month(history, income_flows) if income_flows else None,
    }

    return render(
        request,
        "investments/fragments/detail.html",
        {
            "account": account,
            "perf": perf,
            "home": in_home_currency(perf),
            "transactions": transactions,
            "income": income,
            "income_entities": list(account.income_entities.all()),
            "chart": chart,
        },
    )


@login_required
@require_http_methods(["GET"])
def investment_classes_index(request):
    return render(request, "investment_classes/pages/index.html")


@only_htmx
@login_required
@require_http_methods(["GET"])
def investment_classes_list(request):
    classes = InvestmentClass.objects.all()
    return render(
        request,
        "investment_classes/fragments/list.html",
        {
            "classes": classes,
            "total_target": sum(cls.target or 0 for cls in classes),
        },
    )


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def investment_class_add(request):
    return _investment_class_form(request, InvestmentClass(), _("Asset class added successfully"))


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def investment_class_edit(request, pk):
    cls = get_object_or_404(InvestmentClass, pk=pk)
    return _investment_class_form(request, cls, _("Asset class updated successfully"))


def _investment_class_form(request, instance, success):
    form = InvestmentClassForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, success)
        return HttpResponse(status=204, headers={"HX-Trigger": "updated, hide_offcanvas"})
    return render(
        request,
        "investment_classes/fragments/form.html",
        {"form": form, "object": instance},
    )


@only_htmx
@login_required
@require_http_methods(["DELETE"])
def investment_class_delete(request, pk):
    get_object_or_404(InvestmentClass, pk=pk).delete()
    messages.success(request, _("Asset class deleted successfully"))
    return HttpResponse(status=204, headers={"HX-Trigger": "updated, hide_offcanvas"})
