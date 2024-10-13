import zoneinfo
from django.utils import timezone, translation
from django.utils.cache import patch_vary_headers
from django.utils.translation import activate


class LocalizationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tz = request.COOKIES.get("mytz")
        if request.user.is_authenticated:
            user_settings = request.user.settings
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
            language = user_language
        else:
            language = translation.get_language_from_request(request)

        translation.activate(language)
        request.LANGUAGE_CODE = translation.get_language()

        response = self.get_response(request)

        patch_vary_headers(response, ("Accept-Language",))
        response.headers.setdefault("Content-Language", translation.get_language())

        translation.deactivate()

        return response
