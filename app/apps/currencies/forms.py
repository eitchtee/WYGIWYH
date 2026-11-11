import json

from apps.common.widgets.crispy.daisyui import Switch
from apps.common.widgets.crispy.submit import NoClassSubmit
from apps.common.widgets.datepicker import AirDateTimePickerInput
from apps.common.widgets.decimal import ArbitraryDecimalDisplayNumberInput
from apps.common.widgets.tom_select import TomSelect
from apps.currencies.exchange_rates.fetcher import PROVIDER_MAPPING
from apps.currencies.models import Currency, ExchangeRate, ExchangeRateService
from crispy_forms.bootstrap import FormActions
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Column, Layout, Row
from django import forms
from django.core.exceptions import ValidationError
from django.forms import CharField
from django.utils.translation import gettext_lazy as _


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
            "show_exchanged_amounts",
            "is_archived",
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
            Switch("is_archived"),
            "decimal_places",
            "prefix",
            "suffix",
            "exchange_currency",
            Switch("show_exchanged_amounts"),
        )

        if self.instance and self.instance.pk:
            self.helper.layout.append(
                FormActions(
                    NoClassSubmit("submit", _("Update"), css_class="btn btn-primary"),
                ),
            )
        else:
            self.helper.layout.append(
                FormActions(
                    NoClassSubmit("submit", _("Add"), css_class="btn btn-primary"),
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
                    NoClassSubmit("submit", _("Update"), css_class="btn btn-primary"),
                ),
            )
        else:
            self.helper.layout.append(
                FormActions(
                    NoClassSubmit("submit", _("Add"), css_class="btn btn-primary"),
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
            "options",
            "interval_type",
            "fetch_interval",
            "target_currencies",
            "target_accounts",
            "one_per_day",
            "max_rates",
        ]
        widgets = {"options": forms.Textarea(attrs={"rows": 2})}

    # Shows API Key and Options only for providers that use them
    SERVICE_TYPE_SCRIPT = """
        init send change to me end
        on change js(me)
            const p = JSON.parse(me.dataset.providers)[me.value] || {};
            document.getElementById('div_id_api_key').classList.toggle('hidden', !p.api_key);
            document.getElementById('div_id_options').classList.toggle('hidden', !p.options);
            const help = document.getElementById('id_options_helptext');
            if (help) help.textContent = p.options || '';
        end
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        providers = {
            key: {
                "api_key": provider.requires_api_key(),
                "options": str(provider.options_help or ""),
            }
            for key, provider in PROVIDER_MAPPING.items()
        }
        self.fields["service_type"].widget.attrs.update(
            {"data-providers": json.dumps(providers), "_": self.SERVICE_TYPE_SCRIPT}
        )

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = "post"
        self.helper.layout = Layout(
            "name",
            "service_type",
            Switch("is_active"),
            "api_key",
            "options",
            Row(
                Column("interval_type"),
                Column("fetch_interval"),
            ),
            "target_currencies",
            "target_accounts",
            Switch("one_per_day"),
            "max_rates",
        )

        if self.instance and self.instance.pk:
            self.helper.layout.append(
                FormActions(
                    NoClassSubmit("submit", _("Update"), css_class="btn btn-primary"),
                ),
            )
        else:
            self.helper.layout.append(
                FormActions(
                    NoClassSubmit("submit", _("Add"), css_class="btn btn-primary"),
                ),
            )

    def clean(self):
        cleaned_data = super().clean()
        provider = PROVIDER_MAPPING.get(cleaned_data.get("service_type"))
        if provider:
            try:
                cleaned_data["options"] = provider.clean_options(
                    cleaned_data.get("options") or ""
                )
            except ValidationError as e:
                self.add_error("options", e)
        return cleaned_data
