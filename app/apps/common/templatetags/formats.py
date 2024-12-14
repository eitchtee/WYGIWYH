from django import template
from django.utils.formats import get_format


register = template.Library()


@register.simple_tag
def get_thousand_separator():
    print(get_format("THOUSAND_SEPARATOR"))
    return get_format("THOUSAND_SEPARATOR")


@register.simple_tag
def get_decimal_separator():
    print(get_format("DECIMAL_SEPARATOR"))
    return get_format("DECIMAL_SEPARATOR")
