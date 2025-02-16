from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field, Row, Column
from django import forms
from django.utils.translation import gettext_lazy as _

from apps.common.widgets.datepicker import (
    AirMonthYearPickerInput,
    AirYearPickerInput,
    AirDatePickerInput,
)


class SingleMonthForm(forms.Form):
    month = forms.DateField(
        widget=AirMonthYearPickerInput(clear_button=False), label="", required=False
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.disable_csrf = True

        self.helper.layout = Layout(Field("month"))


class SingleYearForm(forms.Form):
    year = forms.DateField(
        widget=AirYearPickerInput(clear_button=False), label="", required=False
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.disable_csrf = True

        self.helper.layout = Layout(Field("year"))


class MonthRangeForm(forms.Form):
    month_from = forms.DateField(
        widget=AirMonthYearPickerInput(clear_button=False), label="", required=False
    )
    month_to = forms.DateField(
        widget=AirMonthYearPickerInput(clear_button=False), label="", required=False
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.disable_csrf = True

        self.helper.layout = Layout(
            Row(
                Column("month_from", css_class="form-group col-md-6"),
                Column("month_to", css_class="form-group col-md-6"),
            ),
        )


class YearRangeForm(forms.Form):
    year_from = forms.DateField(
        widget=AirYearPickerInput(clear_button=False), label="", required=False
    )
    year_to = forms.DateField(
        widget=AirYearPickerInput(clear_button=False), label="", required=False
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.disable_csrf = True

        self.helper.layout = Layout(
            Row(
                Column("year_from", css_class="form-group col-md-6"),
                Column("year_to", css_class="form-group col-md-6"),
            ),
        )


class DateRangeForm(forms.Form):
    date_from = forms.DateField(
        widget=AirDatePickerInput(clear_button=False), label="", required=False
    )
    date_to = forms.DateField(
        widget=AirDatePickerInput(clear_button=False), label="", required=False
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.disable_csrf = True

        self.helper.layout = Layout(
            Row(
                Column("date_from", css_class="form-group col-md-6"),
                Column("date_to", css_class="form-group col-md-6"),
                css_class="mb-0",
            ),
        )
