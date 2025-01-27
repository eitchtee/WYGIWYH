from django import template

from apps.common.functions.format import get_format

register = template.Library()


@register.simple_tag
def get_thousand_separator():
    return get_format("THOUSAND_SEPARATOR")


@register.simple_tag
def get_decimal_separator():
    return get_format("DECIMAL_SEPARATOR")
