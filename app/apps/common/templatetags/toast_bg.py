from django import template
from django.utils.translation import gettext_lazy as _

register = template.Library()


@register.filter
def toast_bg(tags):
    if "success" in tags:
        return "success"
    elif "warning" in tags:
        return "warning"
    elif "error" in tags:
        return "danger"
    elif "info" in tags:
        return "info"


@register.filter
def toast_icon(tags):
    if "success" in tags:
        return "fa-solid fa-circle-check"
    elif "warning" in tags:
        return "fa-solid fa-circle-exclamation"
    elif "error" in tags:
        return "fa-solid fa-circle-xmark"
    elif "info" in tags:
        return "fa-solid fa-circle-info"


@register.filter
def toast_title(tags):
    if "success" in tags:
        return _("Success")
    elif "warning" in tags:
        return _("Warning")
    elif "error" in tags:
        return _("Error")
    elif "info" in tags:
        return _("Info")
