import zoneinfo
from django.utils import timezone, translation
from django.utils.cache import patch_vary_headers
from django.utils.translation import activate
from cachalot.api import invalidate
import logging

logger = logging.getLogger()


class LocalizationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tz = request.COOKIES.get("mytz")
        logger.info("tz: %s", tz)
        if request.user.is_authenticated:
            user_settings = request.user.settings
            user_language = user_settings.language
            user_timezone = user_settings.timezone
        else:
            user_language = "auto"
            user_timezone = "auto"

        logger.info("lang: %s", user_language)
        logger.info("timezone: %s", user_timezone)

        if tz and user_timezone == "auto":
            timezone.activate(zoneinfo.ZoneInfo(tz))
        elif user_timezone != "auto":
            timezone.activate(zoneinfo.ZoneInfo(user_timezone))
        else:
            timezone.activate(zoneinfo.ZoneInfo("UTC"))

        if user_language and user_language != "auto":
            activate(user_language)
        else:
            detected_language = translation.get_language_from_request(request)
            logger.info("detected_language: %s", detected_language)
            activate(detected_language)

        return self.get_response(request)
