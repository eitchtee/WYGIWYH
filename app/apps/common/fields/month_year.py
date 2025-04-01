import datetime

from django import forms
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.widgets.datepicker import AirMonthYearPickerInput
from apps.common.widgets.month_year import MonthYearWidget


class MonthYearModelField(models.DateField):
    def to_python(self, value):
        if value is None or isinstance(value, datetime.date):
            return value

        try:
            # Parse the input as year-month
            date = datetime.datetime.strptime(value, "%Y-%m")
            # Set the day to 1
            return date.replace(day=1).date()
        except ValueError:
            try:
                # Also accept YYYY-MM-DD format (for loaddata)
                return (
                    datetime.datetime.strptime(value, "%Y-%m-%d").replace(day=1).date()
                )
            except ValueError:
                raise ValidationError(
                    _("Invalid date format. Use YYYY-MM or YYYY-MM-DD.")
                )

    def formfield(self, **kwargs):
        kwargs["widget"] = MonthYearWidget
        kwargs["form_class"] = MonthYearFormField
        return super().formfield(**kwargs)


class MonthYearFormField(forms.DateField):
    widget = AirMonthYearPickerInput

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.input_formats = ["%Y-%m"]

    def to_python(self, value):
        if value in self.empty_values:
            return None
        if isinstance(value, datetime.datetime):
            return value.date()
        try:
            date = datetime.datetime.strptime(value, "%Y-%m")
            return date.replace(day=1).date()
        except ValueError:
            try:
                date = datetime.datetime.strptime(value, "%Y-%m-%d")
                return date.replace(day=1).date()
            except ValueError:
                raise ValidationError(_("Invalid date format. Use YYYY-MM."))

    def prepare_value(self, value):
        if isinstance(value, datetime.date):
            return value.strftime("%Y-%m")
        return value
