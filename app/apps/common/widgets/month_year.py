from datetime import datetime, date

from django import forms


class MonthYearWidget(forms.DateInput):
    """
    Custom widget to display a month-year picker.
    """

    input_type = "month"  # Set the input type to 'month'

    def format_value(self, value):
        if isinstance(value, (datetime, date)):
            return value.strftime("%Y-%m")
        return value
