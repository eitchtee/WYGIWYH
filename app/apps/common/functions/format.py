from apps.common.middleware.thread_local import get_current_user
from django.utils.formats import get_format as original_get_format


def get_format(format_type=None, lang=None, use_l10n=None):
    user = get_current_user()

    if (
        user
        and user.is_authenticated
        and hasattr(user, "settings")
        and use_l10n is not False
    ):
        user_settings = user.settings
        if format_type == "THOUSAND_SEPARATOR":
            number_format = getattr(user_settings, "number_format", None)
            if number_format == "DC":
                return "."
            elif number_format == "CD":
                return ","
            elif number_format == "SD" or number_format == "SC":
                return " "
        elif format_type == "DECIMAL_SEPARATOR":
            number_format = getattr(user_settings, "number_format", None)
            if number_format == "DC" or number_format == "SC":
                return ","
            elif number_format == "CD" or number_format == "SD":
                return "."
        elif format_type == "SHORT_DATE_FORMAT":
            date_format = getattr(user_settings, "date_format", None)
            if date_format and date_format != "SHORT_DATE_FORMAT":
                return date_format
        elif format_type == "SHORT_DATETIME_FORMAT":
            datetime_format = getattr(user_settings, "datetime_format", None)
            if datetime_format and datetime_format != "SHORT_DATETIME_FORMAT":
                return datetime_format

    return original_get_format(format_type, lang, use_l10n)
