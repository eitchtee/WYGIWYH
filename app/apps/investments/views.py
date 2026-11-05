import json

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils.formats import date_format

from apps.accounts.models import Account
from apps.common.decorators.htmx import only_htmx
from apps.common.functions.permissions import READ, get_shared_object_or_error
from apps.investments.services import (
    get_holding_performance,
    in_home_currency,
    income_entity_ids,
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

    chart = {
        "labels": [date_format(p["date"], "M Y") for p in perf.history],
        "value": [float(p["value"]) if p["value"] is not None else None for p in perf.history],
        "invested": [float(p["invested"]) for p in perf.history],
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
            "chart": json.dumps(chart),
        },
    )
