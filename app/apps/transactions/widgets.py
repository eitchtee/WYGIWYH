from datetime import datetime, date

from django import forms
from decimal import Decimal


class MonthYearWidget(forms.DateInput):
    """
    Custom widget to display a month-year picker.
    """

    input_type = "month"  # Set the input type to 'month'

    def format_value(self, value):
        if isinstance(value, (datetime, date)):
            return value.strftime("%Y-%m")
        return value


class ArbitraryDecimalDisplayNumberInput(forms.NumberInput):
    def __init__(self, *args, **kwargs):
        self.decimal_places = kwargs.pop("decimal_places", 2)
        super().__init__(*args, **kwargs)
        self.attrs.update({"step": f".{'0' * (self.decimal_places - 1)}1"})

    def format_value(self, value):
        if value is not None and isinstance(value, Decimal):
            # Strip trailing 0s, leaving a minimum of 2 decimal places
            while (
                abs(value.as_tuple().exponent) > self.decimal_places
                and value.as_tuple().digits[-1] == 0
            ):
                value = Decimal(str(value)[:-1])
        return value
