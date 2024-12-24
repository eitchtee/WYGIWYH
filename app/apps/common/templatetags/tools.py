from django import template

register = template.Library()


@register.filter
def get_dict_item(obj, key):
    if isinstance(obj, dict):
        return obj.get(key)

    return obj
