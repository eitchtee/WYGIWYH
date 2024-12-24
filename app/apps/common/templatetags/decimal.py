from django import template
from decimal import Decimal, DecimalException

from django.utils.formats import number_format
from django.utils.translation import to_locale, get_language

register = template.Library()


@register.filter
def drop_trailing_zeros(value):
    if not isinstance(value, (float, Decimal, str)):
        return value

    try:
        decimal_value = Decimal(str(value))
        return decimal_value.normalize()
    except Exception:
        return value


@register.filter
def localize_number(value, decimal_places=None):
    if value is None:
        return value

    try:
        value = Decimal(str(value))
    except (TypeError, ValueError, DecimalException):
        return value

    return number_format(
        value,
        decimal_pos=decimal_places or abs(value.as_tuple().exponent),
        use_l10n=True,
        force_grouping=True,
    )
