from django import template
from django.template.defaultfilters import date as date_filter
from django.utils import formats, timezone

register = template.Library()


@register.filter
def custom_date(value, user=None):
    if not value:
        return ""

    # Determine if the value is a datetime or just a date
    is_datetime = hasattr(value, "hour")

    # Convert to current timezone if it's a datetime
    if is_datetime and timezone.is_aware(value):
        value = timezone.localtime(value)

    if user and user.is_authenticated:
        user_settings = user.settings

        if is_datetime:
            format_setting = user_settings.datetime_format
        else:
            format_setting = user_settings.date_format

        return formats.date_format(value, format_setting, use_l10n=True)

    return date_filter(
        value, "SHORT_DATE_FORMAT" if not is_datetime else "SHORT_DATETIME_FORMAT"
    )
