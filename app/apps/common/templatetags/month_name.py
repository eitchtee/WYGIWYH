import calendar

from django.template.loader_tags import register
from django.utils.translation import gettext_lazy as _


@register.filter
def month_name(month_number):
    return _(calendar.month_name[month_number])
