from typing import Dict

from django.db.models import Func, F, Value
from django.db.models.functions import Extract
from django.utils import timezone

from apps.currencies.models import ExchangeRate


def get_currency_exchange_map(date=None) -> Dict[str, dict]:
    """
    Creates a nested dictionary of exchange rates and currency information.

    Returns:
    {
        'BTC': {
            'decimal_places': 8,
            'prefix': '₿',
            'suffix': '',
            'rates': {'USD': Decimal('34000.00'), 'EUR': Decimal('31000.00')}
        },
        'USD': {
            'decimal_places': 2,
            'prefix': '$',
            'suffix': '',
            'rates': {'BTC': Decimal('0.0000294'), 'EUR': Decimal('0.91')}
        },
        ...
    }
    """
    if date is None:
        date = timezone.localtime(timezone.now())

    # Get all exchange rates for the closest date
    exchange_rates = (
        ExchangeRate.objects.select_related(
            "from_currency", "to_currency"
        )  # Optimize currency queries
        .annotate(
            date_diff=Func(Extract(F("date") - Value(date), "epoch"), function="ABS"),
            effective_rate=F("rate"),
        )
        .order_by("from_currency", "to_currency", "date_diff")
        .distinct("from_currency", "to_currency")
    )

    # Initialize the result dictionary
    rate_map = {}

    # Build the exchange rate mapping with currency info
    for rate in exchange_rates:
        # Add from_currency info if not exists
        if rate.from_currency.name not in rate_map:
            rate_map[rate.from_currency.name] = {
                "decimal_places": rate.from_currency.decimal_places,
                "prefix": rate.from_currency.prefix,
                "suffix": rate.from_currency.suffix,
                "rates": {},
            }

        # Add to_currency info if not exists
        if rate.to_currency.name not in rate_map:
            rate_map[rate.to_currency.name] = {
                "decimal_places": rate.to_currency.decimal_places,
                "prefix": rate.to_currency.prefix,
                "suffix": rate.to_currency.suffix,
                "rates": {},
            }

        # Add direct rate
        rate_map[rate.from_currency.name]["rates"][rate.to_currency.name] = {
            "rate": rate.rate,
            "decimal_places": rate.to_currency.decimal_places,
            "prefix": rate.to_currency.prefix,
            "suffix": rate.to_currency.suffix,
        }
        # Add inverse rate
        rate_map[rate.to_currency.name]["rates"][rate.from_currency.name] = {
            "rate": 1 / rate.rate,
            "decimal_places": rate.from_currency.decimal_places,
            "prefix": rate.from_currency.prefix,
            "suffix": rate.from_currency.suffix,
        }

    return rate_map
