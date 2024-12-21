from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Row, Column
from django import forms
from apps.currencies.models import Currency
from apps.common.widgets.tom_select import TomSelect


class CurrencyConverterForm(forms.Form):
    from_currency = forms.ModelChoiceField(
        queryset=Currency.objects.all(),
        label="",
        widget=TomSelect(clear_button=False),
    )

    to_currency = forms.ModelChoiceField(
        queryset=Currency.objects.all(),
        label="",
        widget=TomSelect(clear_button=False),
    )

    def __init__(self, *args, **kwargs):
        super(CurrencyConverterForm, self).__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            "from_currency",
            "to_currency",
        )
