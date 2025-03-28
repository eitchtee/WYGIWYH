from django import template
from django.conf import settings

register = template.Library()


@register.simple_tag(name="settings")
def settings_value(name):
    return getattr(settings, name, "")
