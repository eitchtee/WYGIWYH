import zoneinfo
from django.utils import timezone, translation
from django.utils.cache import patch_vary_headers
from django.utils.translation import activate
from cachalot.api import invalidate


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

        # Set timezone
        if tz and user_timezone == "auto":
            timezone_to_activate = zoneinfo.ZoneInfo(tz)
        elif user_timezone != "auto":
            timezone_to_activate = zoneinfo.ZoneInfo(user_timezone)
        else:
            timezone_to_activate = zoneinfo.ZoneInfo("UTC")

        # Set language
        if user_language and user_language != "auto":
            language_to_activate = user_language
        else:
            language_to_activate = translation.get_language_from_request(request)

        # Check if timezone or language has changed
        if (
            getattr(request, "timezone", None) != timezone_to_activate
            or getattr(request, "language", None) != language_to_activate
        ):
            # Invalidate cachalot cache
            invalidate()

        # Apply timezone and language to the request
        request.timezone = timezone_to_activate
        request.language = language_to_activate

        # Wrap the response in a custom function to handle activation
        def wrapped_response(request):
            with timezone.override(request.timezone):
                with translation.override(request.language):
                    return self.get_response(request)

        return wrapped_response(request)
