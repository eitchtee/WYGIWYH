from crispy_forms.bootstrap import FormActions
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Row, Column
from django import forms
from django.utils.translation import gettext_lazy as _

from apps.common.widgets.crispy.submit import NoClassSubmit
from apps.common.widgets.datepicker import AirDatePickerInput
from apps.common.widgets.decimal import ArbitraryDecimalDisplayNumberInput
from apps.common.widgets.tom_select import TomSelect
from apps.dca.models import DCAStrategy, DCAEntry


class DCAStrategyForm(forms.ModelForm):
    class Meta:
        model = DCAStrategy
        fields = ["name", "target_currency", "payment_currency", "notes"]
        widgets = {
            "target_currency": TomSelect(clear_button=False),
            "payment_currency": TomSelect(clear_button=False),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            "name",
            Row(
                Column("payment_currency", css_class="form-group col-md-6"),
                Column("target_currency", css_class="form-group col-md-6"),
            ),
            "notes",
        )

        if self.instance and self.instance.pk:
            self.helper.layout.append(
                FormActions(
                    NoClassSubmit(
                        "submit", _("Update"), css_class="btn btn-outline-primary w-100"
                    ),
                ),
            )
        else:
            self.helper.layout.append(
                FormActions(
                    NoClassSubmit(
                        "submit", _("Add"), css_class="btn btn-outline-primary w-100"
                    ),
                ),
            )


class DCAEntryForm(forms.ModelForm):
    class Meta:
        model = DCAEntry
        fields = [
            "date",
            "amount_paid",
            "amount_received",
            "notes",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, user=None, **kwargs):
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

        if self.instance and self.instance.pk:
            # decimal_places = self.instance.account.currency.decimal_places
            # self.fields["amount"].widget = ArbitraryDecimalDisplayNumberInput(
            #     decimal_places=decimal_places
            # )
            self.helper.layout.append(
                FormActions(
                    NoClassSubmit(
                        "submit", _("Update"), css_class="btn btn-outline-primary w-100"
                    ),
                ),
            )
        else:
            # self.fields["amount"].widget = ArbitraryDecimalDisplayNumberInput()
            self.helper.layout.append(
                FormActions(
                    NoClassSubmit(
                        "submit", _("Add"), css_class="btn btn-outline-primary w-100"
                    ),
                ),
            )

        self.fields["amount_paid"].widget = ArbitraryDecimalDisplayNumberInput()
        self.fields["amount_received"].widget = ArbitraryDecimalDisplayNumberInput()
        self.fields["date"].widget = AirDatePickerInput(clear_button=False, user=user)
