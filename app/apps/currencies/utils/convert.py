from django.db.models import Func, F, Value, DurationField, Case, When, DecimalField, Q
from django.db.models.functions import Abs, Extract
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.currencies.models import ExchangeRate
from apps.currencies.models import Currency


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
            return None, None, None, None

        return (
            amount * exchange_rate.effective_rate,
            to_currency.prefix,
            to_currency.suffix,
            to_currency.decimal_places,
        )
    except ExchangeRate.DoesNotExist:
        return None, None, None, None
