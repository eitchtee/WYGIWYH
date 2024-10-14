import json
from datetime import datetime

from dateutil.relativedelta import relativedelta
from django.core.serializers.json import DjangoJSONEncoder
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone

from apps.net_worth.utils.calculate_net_worth import (
    calculate_currency_net_worth,
    calculate_historical_currency_net_worth,
    calculate_account_net_worth,
    calculate_historical_account_balance,
)
from apps.currencies.models import Currency


# Create your views here.
def net_worth_main(request):
    currency_net_worth = calculate_currency_net_worth()
    account_net_worth = calculate_account_net_worth()

    historical_net_worth = calculate_historical_currency_net_worth()

    labels = list(historical_net_worth.keys())
    currencies = list(historical_net_worth[labels[0]].keys())

    datasets = []
    for i, currency in enumerate(currencies):
        data = [
            float(month_data[currency]) for month_data in historical_net_worth.values()
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

    labels = list(historical_account_balance.keys())
    accounts = list(historical_account_balance[labels[0]].keys())

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
