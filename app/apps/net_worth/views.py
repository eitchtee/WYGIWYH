from datetime import datetime

from django.http import JsonResponse
from django.shortcuts import render

from apps.net_worth.utils.calculate_net_worth import (
    calculate_net_worth,
    calculate_historical_net_worth,
)
from apps.currencies.models import Currency


# Create your views here.
def net_worth_main(request):
    net_worth = calculate_net_worth()
    # historical = calculate_historical_net_worth(
    #     start_date=datetime(day=1, month=1, year=2021).date(),
    #     end_date=datetime(day=1, month=1, year=2025).date(),
    # )
    # print(historical)

    # Format the net worth with currency details
    formatted_net_worth = []
    for currency_code, amount in net_worth.items():
        currency = Currency.objects.get(code=currency_code)
        formatted_net_worth.append(
            {
                "amount": amount,
                "code": currency.code,
                "name": currency.name,
                "prefix": currency.prefix,
                "suffix": currency.suffix,
                "decimal_places": currency.decimal_places,
            }
        )

    return render(
        request, "net_worth/net_worth.html", {"currency_net_worth": formatted_net_worth}
    )
