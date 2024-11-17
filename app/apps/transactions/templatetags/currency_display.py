from decimal import Decimal

from django import template
from django.utils.formats import number_format


register = template.Library()


def _format_string(prefix, amount, decimal_places, suffix):
    if isinstance(amount, (int, float, Decimal)):
        formatted_amount = number_format(
            value=abs(amount), decimal_pos=decimal_places, force_grouping=True
        )
        if amount < 0:
            return f"-{prefix}{formatted_amount}{suffix}"
        else:
            return f"{prefix}{formatted_amount}{suffix}"
    else:
        return "ERR"


@register.simple_tag(name="currency_display")
def currency_display(amount, prefix, suffix, decimal_places):
    return _format_string(prefix, amount, decimal_places, suffix)
