from django import template
from django.utils import timezone
from datetime import date
from django.utils.translation import gettext_lazy as _, ngettext_lazy

from django.utils.formats import date_format

register = template.Library()


@register.filter(name="customnaturaldate")
def naturaldate(value):
    if not isinstance(value, date):
        return value

    today = timezone.localdate(timezone.now())
    delta = value - today

    if delta.days == 0:
        return _("today")
    elif delta.days == 1:
        return _("tomorrow")
    elif delta.days == -1:
        return _("yesterday")
    elif -7 <= delta.days < 0:
        return _("last 7 days")
    elif 0 < delta.days <= 7:
        return _("in the next 7 days")
    elif delta.days < -365:
        years = abs(delta.days) // 365
        return ngettext_lazy("%(years)s year ago", "%(years)s years ago", years) % {
            "years": years
        }
    elif delta.days < -30:
        months = abs(delta.days) // 30
        return ngettext_lazy(
            "%(months)s month ago", "%(months)s months ago", months
        ) % {"months": months}
    elif delta.days < -7:
        weeks = abs(delta.days) // 7
        return ngettext_lazy("%(weeks)s week ago", "%(weeks)s weeks ago", weeks) % {
            "weeks": weeks
        }
    elif delta.days > 365:
        years = delta.days // 365
        return ngettext_lazy("in %(years)s year", "in %(years)s years", years) % {
            "years": years
        }
    elif delta.days > 30:
        months = delta.days // 30
        return ngettext_lazy("in %(months)s month", "in %(months)s months", months) % {
            "months": months
        }
    elif delta.days > 7:
        weeks = delta.days // 7
        return ngettext_lazy("in %(weeks)s week", "in %(weeks)s weeks", weeks) % {
            "weeks": weeks
        }
    else:
        return date_format(value, format="DATE_FORMAT")
