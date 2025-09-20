import json

from django.contrib.auth.decorators import login_required
from django.core.serializers.json import DjangoJSONEncoder
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods

from apps.net_worth.utils.calculate_net_worth import (
    calculate_historical_currency_net_worth,
    calculate_historical_account_balance,
    calculate_monthly_net_worth_difference,
)
from apps.transactions.models import Transaction
from apps.transactions.utils.calculations import (
    calculate_currency_totals,
    calculate_account_totals,
)


@login_required
@require_http_methods(["GET"])
def net_worth(request):
    if "view_type" in request.GET:
        view_type = request.GET["view_type"]
        request.session["networth_view_type"] = view_type
    else:
        view_type = request.session.get("networth_view_type", "current")

    if view_type == "current":
        transactions_currency_queryset = (
            Transaction.objects.filter(is_paid=True, account__is_archived=False)
            .order_by(
                "account__currency__name",
            )
            .exclude(account__in=request.user.untracked_accounts.all())
        )
        transactions_account_queryset = Transaction.objects.filter(
            is_paid=True, account__is_archived=False
        ).order_by(
            "account__group__name",
            "account__name",
        )
    else:
        transactions_currency_queryset = (
            Transaction.objects.filter(account__is_archived=False)
            .order_by(
                "account__currency__name",
            )
            .exclude(account__in=request.user.untracked_accounts.all())
        )
        transactions_account_queryset = Transaction.objects.filter(
            account__is_archived=False
        ).order_by(
            "account__group__name",
            "account__name",
        )

    currency_net_worth = calculate_currency_totals(
        transactions_queryset=transactions_currency_queryset, deep_search=True
    )
    account_net_worth = calculate_account_totals(
        transactions_queryset=transactions_account_queryset
    )

    historical_currency_net_worth = calculate_historical_currency_net_worth(
        queryset=transactions_currency_queryset
    )

    labels = (
        list(historical_currency_net_worth.keys())
        if historical_currency_net_worth
        else []
    )
    currencies = (
        list(historical_currency_net_worth[labels[0]].keys())
        if historical_currency_net_worth
        else []
    )

    datasets = []
    for i, currency in enumerate(currencies):
        data = [
            float(month_data[currency])
            for month_data in historical_currency_net_worth.values()
        ]
        datasets.append(
            {
                "label": currency,
                "data": data,
                "yAxisID": f"y{i}",
                "fill": False,
                "tension": 0.1,
            }
        )

    chart_data_currency = {"labels": labels, "datasets": datasets}

    chart_data_currency_json = json.dumps(chart_data_currency, cls=DjangoJSONEncoder)

    monthly_difference_data = calculate_monthly_net_worth_difference(
        historical_net_worth=historical_currency_net_worth
    )

    diff_labels = (
        list(monthly_difference_data.keys()) if monthly_difference_data else []
    )
    diff_currencies = (
        list(monthly_difference_data[diff_labels[0]].keys())
        if monthly_difference_data and diff_labels
        else []
    )

    diff_datasets = []
    for i, currency in enumerate(diff_currencies):
        data = [
            float(month_data.get(currency, 0))
            for month_data in monthly_difference_data.values()
        ]
        diff_datasets.append(
            {
                "label": currency,
                "data": data,
                "borderWidth": 3,
            }
        )

    chart_data_monthly_difference = {"labels": diff_labels, "datasets": diff_datasets}
    chart_data_monthly_difference_json = json.dumps(
        chart_data_monthly_difference, cls=DjangoJSONEncoder
    )

    historical_account_balance = calculate_historical_account_balance(
        queryset=transactions_account_queryset
    )

    labels = (
        list(historical_account_balance.keys()) if historical_account_balance else []
    )
    accounts = (
        list(historical_account_balance[labels[0]].keys())
        if historical_account_balance
        else []
    )

    datasets = []
    for i, account in enumerate(accounts):
        data = [
            float(month_data[account])
            for month_data in historical_account_balance.values()
        ]
        datasets.append(
            {
                "label": account,
                "data": data,
                "fill": False,
                "tension": 0.1,
                "yAxisID": f"y-axis-{i}",  # Assign each dataset to its own Y-axis
            }
        )

    chart_data_accounts = {"labels": labels, "datasets": datasets}

    chart_data_accounts_json = json.dumps(chart_data_accounts, cls=DjangoJSONEncoder)

    return render(
        request,
        "net_worth/net_worth.html",
        {
            "currency_net_worth": currency_net_worth,
            "account_net_worth": account_net_worth,
            "chart_data_currency_json": chart_data_currency_json,
            "currencies": currencies,
            "chart_data_accounts_json": chart_data_accounts_json,
            "accounts": accounts,
            "type": view_type,
            "chart_data_monthly_difference_json": chart_data_monthly_difference_json,
        },
    )


@login_required
@require_http_methods(["GET"])
def net_worth_current(request):
    request.session["networth_view_type"] = "current"

    return redirect("net_worth")


@login_required
@require_http_methods(["GET"])
def net_worth_projected(request):
    request.session["networth_view_type"] = "projected"

    return redirect("net_worth")
