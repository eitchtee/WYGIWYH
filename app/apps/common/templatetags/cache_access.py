from django import template
from django.conf import settings
from django.core.cache import caches
from packaging.version import InvalidVersion, parse as parse_version

register = template.Library()


@register.simple_tag
def get_update_check():
    """
    Compares the latest GitHub release (cached by the check_for_updates task)
    against the running APP_VERSION.
    """
    latest_version = caches["update_check"].get("latest_version")
    # The cached tag never expires, so opting out must also hide what was found before
    if not settings.CHECK_FOR_UPDATES or not latest_version:
        return {"update_available": False, "latest_version": "N/A"}

    try:
        update_available = parse_version(latest_version) > parse_version(settings.APP_VERSION)
    except InvalidVersion:
        # Builds without a real version (dev, "unknown") can't be compared, so don't claim an update
        update_available = False

    return {"update_available": update_available, "latest_version": latest_version}
