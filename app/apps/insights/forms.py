from apps.common.widgets.datepicker import (
    AirDatePickerInput,
    AirMonthYearPickerInput,
    AirYearPickerInput,
)
from apps.common.widgets.tom_select import TomSelect
from apps.transactions.models import TransactionCategory
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Column, Field, Layout, Row
from django import forms
from django.utils.translation import gettext_lazy as _


class SingleMonthForm(forms.Form):
    month = forms.DateField(
        widget=AirMonthYearPickerInput(clear_button=False), label="", required=True
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.disable_csrf = True

        self.helper.layout = Layout(Field("month"))


class SingleYearForm(forms.Form):
    year = forms.DateField(
        widget=AirYearPickerInput(clear_button=False), label="", required=True
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.disable_csrf = True

        self.helper.layout = Layout(Field("year"))


class MonthRangeForm(forms.Form):
    month_from = forms.DateField(
        widget=AirMonthYearPickerInput(clear_button=False), label="", required=True
    )
    month_to = forms.DateField(
        widget=AirMonthYearPickerInput(clear_button=False), label="", required=True
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.disable_csrf = True

        self.helper.layout = Layout(
            Row(
                Column("month_from", css_class="md:col-span-6"),
                Column("month_to", css_class="md:col-span-6"),
            ),
        )


class YearRangeForm(forms.Form):
    year_from = forms.DateField(
        widget=AirYearPickerInput(clear_button=False), label="", required=True
    )
    year_to = forms.DateField(
        widget=AirYearPickerInput(clear_button=False), label="", required=True
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.disable_csrf = True

        self.helper.layout = Layout(
            Row(
                Column("year_from", css_class="md:col-span-6"),
                Column("year_to", css_class="md:col-span-6"),
            ),
        )


class DateRangeForm(forms.Form):
    date_from = forms.DateField(
        widget=AirDatePickerInput(clear_button=False), label="", required=True
    )
    date_to = forms.DateField(
        widget=AirDatePickerInput(clear_button=False), label="", required=True
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.disable_csrf = True

        self.helper.layout = Layout(
            Row(
                Column("date_from", css_class="md:col-span-6"),
                Column("date_to", css_class="md:col-span-6"),
                css_class="mb-0",
            ),
        )


class CategoryForm(forms.Form):
    category = forms.ModelChoiceField(
        required=False,
        label=_("Category"),
        empty_label=_("Uncategorized"),
        queryset=TransactionCategory.objects.all(),
        widget=TomSelect(clear_button=True),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["category"].queryset = TransactionCategory.objects.all()

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.disable_csrf = True

        self.helper.layout = Layout("category")
