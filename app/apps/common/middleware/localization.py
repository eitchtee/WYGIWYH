import zoneinfo

from django.utils import formats
from django.utils import timezone, translation
from django.utils.functional import lazy

from apps.common.functions.format import get_format as custom_get_format
from apps.users.models import UserSettings


class LocalizationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.patch_get_format()

    def __call__(self, request):
        tz = request.COOKIES.get("mytz")
        if request.user.is_authenticated and hasattr(request.user, "settings"):
            user_settings = request.user.settings
            user_language = user_settings.language
            user_timezone = user_settings.timezone
        elif request.user.is_authenticated and not hasattr(request.user, "settings"):
            # Create UserSettings if it doesn't exist
            UserSettings.objects.create(user=request.user)
            user_language = "auto"
            user_timezone = "auto"
        else:
            user_language = "auto"
            user_timezone = "auto"

        if tz and user_timezone == "auto":
            timezone.activate(zoneinfo.ZoneInfo(tz))
        elif user_timezone != "auto":
            timezone.activate(zoneinfo.ZoneInfo(user_timezone))
        else:
            timezone.activate(zoneinfo.ZoneInfo("UTC"))

        if user_language and user_language != "auto":
            translation.activate(user_language)
        else:
            detected_language = translation.get_language_from_request(request)
            translation.activate(detected_language)

        return self.get_response(request)

    @staticmethod
    def patch_get_format():
        formats.get_format = custom_get_format
        formats.get_format_lazy = lazy(custom_get_format, str, list, tuple)
