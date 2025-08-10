from decimal import Decimal, InvalidOperation

from django import forms
from django.utils.formats import number_format

from apps.common.functions.format import get_format


def convert_to_decimal(value: str):
    # Remove any whitespace
    value = value.strip()

    # Get the thousand and decimal separators from Django's localization settings
    thousands_sep = get_format("THOUSAND_SEPARATOR")
    decimal_sep = get_format("DECIMAL_SEPARATOR")

    # Remove thousands separators and replace decimal separator with '.'
    value = value.replace(thousands_sep, "")
    value = value.replace(decimal_sep, ".")

    # Convert to Decimal
    if value:
        return Decimal(value)
    return None


class ArbitraryDecimalDisplayNumberInput(forms.TextInput):
    """A widget for displaying and inputing decimal numbers with the least amount of trailing zeros possible. You
    must set this on your Form's __init__ method."""

    def __init__(self, *args, **kwargs):
        self.decimal_places = kwargs.pop("decimal_places", None)
        self.type = "text"
        super().__init__(*args, **kwargs)
        self.attrs.update(
            {
                "x-data": "",
                "x-mask:dynamic": f"$money($input, '{get_format('DECIMAL_SEPARATOR')}', '{get_format('THOUSAND_SEPARATOR')}', '30')",
                "x-on:keyup": "$el.dispatchEvent(new Event('input'))",
            }
        )

    def format_value(self, value):
        if value is not None and isinstance(value, (Decimal, float, str)):
            try:
                # Convert to Decimal if it's a float or string
                if isinstance(value, float):
                    value = Decimal(value)
                elif isinstance(value, str):
                    value = Decimal(convert_to_decimal(value))

                # Remove trailing zeros
                value = value.normalize()

                # Format the number using Django's localization
                formatted_value = number_format(
                    value,
                    force_grouping=False,
                    decimal_pos=self.decimal_places,
                )

                return formatted_value
            except (InvalidOperation, ValueError):
                # If there's an error in conversion, return the original value
                return value
        return value

    def value_from_datadict(self, data, files, name):
        value = super().value_from_datadict(data, files, name)
        if value is not None:
            # Remove any non-numeric characters except for the decimal point
            value = convert_to_decimal(value)

        return value
