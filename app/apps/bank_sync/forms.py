import copy

from crispy_forms.bootstrap import FormActions
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout
from django import forms
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import Account
from apps.bank_sync.models import BankSyncAccount, BankSyncService
from apps.bank_sync.providers import PROVIDER_MAPPING
from apps.common.widgets.crispy.daisyui import Switch
from apps.common.widgets.crispy.submit import NoClassSubmit
from apps.common.widgets.datepicker import AirDatePickerInput

SETTING_PREFIX = "setting_"


class BankSyncServiceForm(forms.ModelForm):
    class Meta:
        model = BankSyncService
        fields = [
            "name",
            "service_type",
            "is_active",
            "sync_interval",
            "trigger_rules",
            "match_existing",
        ]

    def __init__(self, *args, refresh_url=None, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance.pk:
            # Synced ids and links belong to the provider, it can't change
            self.fields["service_type"].disabled = True
            service_type = self.instance.service_type
        else:
            # The provider's own settings depend on the selected service type
            service_type = self.data.get("service_type") or self.initial.get(
                "service_type"
            )
        provider = PROVIDER_MAPPING.get(service_type)
        self.setting_names = []
        for key, field in (provider.settings_fields if provider else {}).items():
            name = SETTING_PREFIX + key
            self.fields[name] = copy.deepcopy(field)
            if key in self.instance.settings:
                self.initial.setdefault(name, self.instance.settings[key])
            self.setting_names.append(name)

        # Re-renders the form with the new provider's fields
        self.fields["service_type"].widget.attrs.update(
            {
                "hx-get": refresh_url,
                "hx-include": "closest form",
                "hx-target": "#generic-offcanvas",
                "hx-trigger": "change",
            }
        )

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            "name",
            "service_type",
            *self.setting_names,
            Switch("is_active"),
            Switch("trigger_rules"),
            Switch("match_existing"),
            "sync_interval",
            FormActions(
                NoClassSubmit(
                    "submit",
                    _("Update") if self.instance.pk else _("Add"),
                    css_class="btn btn-primary",
                ),
            ),
        )

    def save(self, commit=True):
        self.instance.settings = {
            name.removeprefix(SETTING_PREFIX): self.cleaned_data[name]
            for name in self.setting_names
        }
        return super().save(commit)


class BankSyncAccountForm(forms.ModelForm):
    currencies = forms.MultipleChoiceField(
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label=_("Currencies"),
        help_text=_("Only sync transactions in these currencies. Empty syncs all."),
    )

    class Meta:
        model = BankSyncAccount
        fields = ["account", "start_date", "currencies"]
        widgets = {"start_date": AirDatePickerInput(clear_button=False)}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Keeps an account archived after being linked, or the whole formset fails
        self.fields["account"].queryset = Account.objects.filter(
            Q(is_archived=False) | Q(pk=self.instance.account_id)
        ).select_related("currency")
        self.fields["account"].empty_label = _("Don't sync")
        self.fields["currencies"].choices = [
            (code, code)
            for code in sorted(
                set(self.instance.available_currencies) | set(self.instance.currencies)
            )
        ]

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("account") and not cleaned_data.get("start_date"):
            self.add_error("start_date", _("Required when an account is set."))
        return cleaned_data


BankSyncAccountFormSet = forms.modelformset_factory(
    BankSyncAccount, form=BankSyncAccountForm, extra=0
)
