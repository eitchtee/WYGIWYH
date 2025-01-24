import json

from django import template


register = template.Library()


@register.filter("json")
def convert_to_json(value):
    return json.dumps(value)
