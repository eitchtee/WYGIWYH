from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


def validate_decimal_places(value):
    if abs(value.as_tuple().exponent) > 30:
        raise ValidationError(
            _("%(value)s has too many decimal places. Maximum is 30."),
            params={"value": value},
        )


def validate_non_negative(value):
    if value < 0:
        raise ValidationError(
            _("%(value)s is not a non-negative number"),
            params={"value": value},
        )
