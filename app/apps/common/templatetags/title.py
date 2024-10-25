from django import template
from django.conf import settings

register = template.Library()


@register.filter
def site_title(value):
    value = value.strip()
    if value:
        return f"{value} {settings.TITLE_SEPARATOR or '::'} {settings.SITE_TITLE or 'SITE_TITLE NOT SET'}"
    else:
        return settings.SITE_TITLE or "SITE_TITLE NOT SET"
