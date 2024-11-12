from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Row, Column
from django.utils.translation import gettext_lazy as _

from .models import DCAStrategy, DCAEntry
from apps.common.widgets.decimal import ArbitraryDecimalDisplayNumberInput


class DCAStrategyForm(forms.ModelForm):
    class Meta:
        model = DCAStrategy
        fields = ["name", "target_currency", "payment_currency", "notes"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            "name",
            Row(
                Column("target_currency", css_class="form-group col-md-6"),
                Column("payment_currency", css_class="form-group col-md-6"),
            ),
            "notes",
        )


class DCAEntryForm(forms.ModelForm):
    class Meta:
        model = DCAEntry
        fields = [
            "date",
            "amount_paid",
            "amount_received",
            "expense_transaction",
            "income_transaction",
            "notes",
        ]
        widgets = {
            "amount_paid": ArbitraryDecimalDisplayNumberInput(decimal_places=8),
            "amount_received": ArbitraryDecimalDisplayNumberInput(decimal_places=8),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            "date",
            Row(
                Column("amount_paid", css_class="form-group col-md-6"),
                Column("amount_received", css_class="form-group col-md-6"),
            ),
            Row(
                Column("expense_transaction", css_class="form-group col-md-6"),
                Column("income_transaction", css_class="form-group col-md-6"),
            ),
            "notes",
        )
