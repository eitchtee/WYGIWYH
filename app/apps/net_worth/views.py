import json

from django.core.serializers.json import DjangoJSONEncoder
from django.shortcuts import render

from apps.net_worth.utils.calculate_net_worth import (
    calculate_currency_net_worth,
    calculate_historical_currency_net_worth,
    calculate_account_net_worth,
    calculate_historical_account_balance,
)


# Create your views here.
def net_worth_main(request):
    currency_net_worth = calculate_currency_net_worth()
    account_net_worth = calculate_account_net_worth()

    historical_currency_net_worth = calculate_historical_currency_net_worth()

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

    historical_account_balance = calculate_historical_account_balance()

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
            "currency_net_worth": currency_net_worth.values(),
            "account_net_worth": account_net_worth,
            "chart_data_currency_json": chart_data_currency_json,
            "currencies": currencies,
            "chart_data_accounts_json": chart_data_accounts_json,
            "accounts": accounts,
        },
    )
