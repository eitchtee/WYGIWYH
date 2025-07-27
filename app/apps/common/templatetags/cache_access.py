# core/templatetags/update_tags.py
from django import template
from django.core.cache import cache

register = template.Library()


@register.simple_tag
def get_update_check():
    """
    Retrieves the update status dictionary from the cache.
    Returns a default dictionary if nothing is found.
    """
    return cache.get("update_check") or {
        "update_available": False,
        "latest_version": "N/A",
    }
