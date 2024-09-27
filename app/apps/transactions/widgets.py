from datetime import datetime, date

from django import forms
from decimal import Decimal

from django.template.defaultfilters import floatformat
from django.utils.formats import get_format


def convert_to_decimal(value):
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


class MonthYearWidget(forms.DateInput):
    """
    Custom widget to display a month-year picker.
    """

    input_type = "month"  # Set the input type to 'month'

    def format_value(self, value):
        if isinstance(value, (datetime, date)):
            return value.strftime("%Y-%m")
        return value


class ArbitraryDecimalDisplayNumberInput(forms.TextInput):
    """A widget for displaying and inputing decimal numbers with the least amount of trailing zeros possible. You
    must set this on your Form's __init__ method."""
    def __init__(self, *args, **kwargs):
        self.decimal_places = kwargs.pop("decimal_places", 2)
        self.type = "text"
        super().__init__(*args, **kwargs)
        self.attrs.update(
            {
                "x-mask:dynamic": f"$money($input, '{get_format('DECIMAL_SEPARATOR')}', "
                f"'{get_format('THOUSAND_SEPARATOR')}', '30')"
            }
        )

    def format_value(self, value):
        if value is not None and isinstance(value, Decimal):
            # Strip trailing 0s, leaving a minimum of 2 decimal places
            while (
                abs(value.as_tuple().exponent) > self.decimal_places
                and value.as_tuple().digits[-1] == 0
            ):
                value = Decimal(str(value)[:-1])

            value = floatformat(value, f"{self.decimal_places}g")
        return value

    def value_from_datadict(self, data, files, name):
        value = super().value_from_datadict(data, files, name)
        if value is not None:
            # Remove any non-numeric characters except for the decimal point
            value = convert_to_decimal(value)

        return value
