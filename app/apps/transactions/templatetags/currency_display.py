from django import template
from django.utils.formats import number_format

from apps.transactions.models import Transaction

register = template.Library()


def _format_string(prefix, amount, decimal_places, suffix):
    formatted_amount = number_format(
        value=abs(amount), decimal_pos=decimal_places, force_grouping=True
    )
    if amount < 0:
        return f"-{prefix}{formatted_amount}{suffix}"
    else:
        return f"{prefix}{formatted_amount}{suffix}"


@register.simple_tag(name="transaction_amount")
def transaction_currency(transaction: Transaction):
    prefix = transaction.account.currency.prefix
    amount = transaction.amount
    decimal_places = transaction.account.currency.decimal_places
    suffix = transaction.account.currency.suffix

    return _format_string(prefix, amount, decimal_places, suffix)


@register.simple_tag(name="entry_amount")
def entry_currency(entry):
    prefix = entry["prefix"]
    amount = entry["amount"]
    decimal_places = entry["decimal_places"]
    suffix = entry["suffix"]

    return _format_string(prefix, amount, decimal_places, suffix)


@register.simple_tag(name="currency_display")
def currency_display(amount, prefix, suffix, decimal_places):
    return _format_string(prefix, amount, decimal_places, suffix)
