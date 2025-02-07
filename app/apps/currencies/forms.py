from crispy_bootstrap5.bootstrap5 import Switch
from crispy_forms.bootstrap import FormActions
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Row, Column
from django import forms
from django.forms import CharField
from django.utils.translation import gettext_lazy as _

from apps.common.widgets.crispy.submit import NoClassSubmit
from apps.common.widgets.datepicker import AirDateTimePickerInput
from apps.common.widgets.decimal import ArbitraryDecimalDisplayNumberInput
from apps.common.widgets.tom_select import TomSelect
from apps.currencies.models import Currency, ExchangeRate, ExchangeRateService


class CurrencyForm(forms.ModelForm):
    prefix = CharField(strip=False, required=False, label=_("Prefix"))
    suffix = CharField(strip=False, required=False, label=_("Suffix"))

    class Meta:
        model = Currency
        fields = [
            "name",
            "decimal_places",
            "prefix",
            "suffix",
            "code",
            "exchange_currency",
        ]
        widgets = {
            "exchange_currency": TomSelect(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = "post"
        self.helper.layout = Layout(
            "code",
            "name",
            "decimal_places",
            "prefix",
            "suffix",
            "exchange_currency",
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


class ExchangeRateForm(forms.ModelForm):
    date = forms.DateTimeField(
        label=_("Date"),
    )

    class Meta:
        model = ExchangeRate
        fields = ["from_currency", "to_currency", "rate", "date"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = "post"
        self.helper.layout = Layout("date", "from_currency", "to_currency", "rate")

        self.fields["rate"].widget = ArbitraryDecimalDisplayNumberInput()
        self.fields["date"].widget = AirDateTimePickerInput(clear_button=False)

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


class ExchangeRateServiceForm(forms.ModelForm):
    class Meta:
        model = ExchangeRateService
        fields = [
            "name",
            "service_type",
            "is_active",
            "api_key",
            "interval_type",
            "fetch_interval",
            "target_currencies",
            "target_accounts",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = "post"
        self.helper.layout = Layout(
            "name",
            "service_type",
            Switch("is_active"),
            "api_key",
            Row(
                Column("interval_type", css_class="form-group col-md-6"),
                Column("fetch_interval", css_class="form-group col-md-6"),
            ),
            "target_currencies",
            "target_accounts",
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
