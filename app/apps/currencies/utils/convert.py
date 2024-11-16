import datetime

from django.db.models import Func, F, Value, Case, When, DecimalField, Q
from django.db.models.functions import Extract
from django.utils import timezone

from apps.currencies.models import Currency
from apps.currencies.models import ExchangeRate


def get_exchange_rate(
    from_currency: Currency, to_currency: Currency, date: datetime.date
) -> ExchangeRate | None:
    try:
        exchange_rate = (
            ExchangeRate.objects.filter(
                Q(from_currency=from_currency, to_currency=to_currency)
                | Q(from_currency=to_currency, to_currency=from_currency)
            )
            .annotate(
                date_diff=Func(
                    Extract(F("date") - Value(date), "epoch"), function="ABS"
                ),
                effective_rate=Case(
                    When(from_currency=from_currency, then=F("rate")),
                    default=1 / F("rate"),
                    output_field=DecimalField(),
                ),
            )
            .order_by("date_diff")
            .first()
        )

        if exchange_rate is None:
            return None

    except ExchangeRate.DoesNotExist:
        return None

    else:
        return exchange_rate


def convert(amount, from_currency: Currency, to_currency: Currency, date=None):
    if from_currency == to_currency:
        return (
            amount,
            to_currency.prefix,
            to_currency.suffix,
            to_currency.decimal_places,
        )

    if date is None:
        date = timezone.localtime(timezone.now())

    exchange_rate = get_exchange_rate(
        from_currency=from_currency, to_currency=to_currency, date=date
    )

    if exchange_rate is None:
        return None, None, None, None

    return (
        amount * exchange_rate.effective_rate,
        to_currency.prefix,
        to_currency.suffix,
        to_currency.decimal_places,
    )
