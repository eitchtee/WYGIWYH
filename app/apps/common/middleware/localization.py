import zoneinfo
from django.utils import timezone
from django.utils.translation import activate

from apps.users.utils.user_settings import ensure_user_settings


class LocalizationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tz = request.COOKIES.get("mytz")
        if request.user.is_authenticated:
            user_settings = ensure_user_settings(request.user)
            user_language = user_settings.language
            user_timezone = user_settings.timezone
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
            activate(user_language)

        return self.get_response(request)
