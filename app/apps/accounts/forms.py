import calendar

from apps.accounts.models import Account, AccountGroup
from apps.common.fields.forms.dynamic_select import (
    DynamicModelChoiceField,
    DynamicModelMultipleChoiceField,
)
from apps.common.widgets.crispy.daisyui import Switch
from apps.common.widgets.crispy.submit import NoClassSubmit
from apps.common.widgets.datepicker import AirDatePickerInput, AirMonthYearPickerInput
from apps.common.widgets.decimal import ArbitraryDecimalDisplayNumberInput
from apps.common.widgets.tom_select import TomSelect
from apps.currencies.models import Currency
from apps.transactions.models import TransactionCategory, TransactionTag
from crispy_forms.bootstrap import FormActions
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Column, Field, Layout, Row
from django import forms
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class AccountGroupForm(forms.ModelForm):
    class Meta:
        model = AccountGroup
        fields = ["name"]
        labels = {"name": _("Group name")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = "post"
        self.helper.layout = Layout(
            "name",
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


class AccountForm(forms.ModelForm):
    group = DynamicModelChoiceField(
        create_field="name",
        label=_("Group"),
        model=AccountGroup,
        required=False,
    )

    class Meta:
        model = Account
        fields = [
            "name",
            "group",
            "currency",
            "exchange_currency",
            "is_asset",
            "is_archived",
        ]
        widgets = {
            "currency": TomSelect(),
            "exchange_currency": TomSelect(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["group"].queryset = AccountGroup.objects.all()

        if self.instance.id:
            qs = Currency.objects.filter(
                Q(is_archived=False) | Q(accounts=self.instance.id)
            ).distinct()
            self.fields["currency"].queryset = qs
            self.fields["exchange_currency"].queryset = qs

        else:
            qs = Currency.objects.filter(Q(is_archived=False))
            self.fields["currency"].queryset = qs
            self.fields["exchange_currency"].queryset = qs

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = "post"
        self.helper.layout = Layout(
            "name",
            "group",
            Switch("is_asset"),
            Switch("is_archived"),
            "currency",
            "exchange_currency",
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


class AccountBalanceForm(forms.Form):
    account_id = forms.IntegerField(widget=forms.HiddenInput())
    new_balance = forms.DecimalField(
        max_digits=42, decimal_places=30, required=False, label=_("New balance")
    )
    category = DynamicModelChoiceField(
        create_field="name",
        model=TransactionCategory,
        required=False,
        label=_("Category"),
    )
    tags = DynamicModelMultipleChoiceField(
        model=TransactionTag,
        to_field_name="name",
        create_field="name",
        required=False,
        label=_("Tags"),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.currency_suffix = self.initial.get("suffix", "")
        self.currency_prefix = self.initial.get("prefix", "")
        self.currency_decimal_places = self.initial.get("decimal_places", 2)
        self.account_name = self.initial.get("account_name", "")
        self.account_group = self.initial.get("account_group", None)
        self.current_balance = self.initial.get("current_balance", 0)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            "new_balance",
            Row(
                Column("category"),
                Column("tags"),
            ),
            Field("account_id"),
        )

        self.fields["new_balance"].widget = ArbitraryDecimalDisplayNumberInput(
            decimal_places=self.currency_decimal_places
        )

        self.fields["category"].queryset = TransactionCategory.objects.filter(
            active=True
        )

        self.fields["tags"].queryset = TransactionTag.objects.filter(active=True)


class ReconciliationCutoffForm(forms.Form):
    """Which transactions the reconciliation balance is computed against."""

    MODE_CURRENT = "current"
    MODE_DATE = "date"
    MODE_MONTH = "month"

    mode = forms.ChoiceField(
        choices=[
            (MODE_CURRENT, _("All paid transactions")),
            (MODE_DATE, _("Up to date")),
            (MODE_MONTH, _("Up to reference month")),
        ],
        required=False,
        initial=MODE_CURRENT,
        label=_("Balance against"),
    )
    date = forms.DateField(
        required=False,
        label=_("Date"),
        widget=AirDatePickerInput(clear_button=False),
    )
    month = forms.DateField(
        required=False,
        label=_("Reference month"),
        widget=AirMonthYearPickerInput(clear_button=False),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, prefix="cutoff", **kwargs)
        today = timezone.localdate(timezone.now())
        self.today = today
        self.fields["date"].initial = today
        self.fields["month"].initial = today.replace(day=1)

    def _value(self, name):
        # Bound but invalid/empty values fall back to the field's initial.
        if self.is_bound and self.is_valid() and self.cleaned_data.get(name):
            return self.cleaned_data[name]
        return self.fields[name].initial

    @property
    def selected_mode(self):
        return self._value("mode")

    def balance_filters(self) -> dict:
        """Extra kwargs for get_account_balance."""
        if self.selected_mode == self.MODE_DATE:
            return {"date_lte": self._value("date")}
        if self.selected_mode == self.MODE_MONTH:
            return {"reference_date_lte": self._value("month")}
        return {}

    def adjustment_dates(self):
        """(date, reference_date) for the reconciliation transaction.

        Dated at the cutoff so a later reconcile with the same or later cutoff
        includes it, and an earlier one doesn't.
        """
        if self.selected_mode == self.MODE_DATE:
            cutoff = self._value("date")
            return cutoff, cutoff.replace(day=1)
        if self.selected_mode == self.MODE_MONTH:
            month = self._value("month")
            last_day = month.replace(
                day=calendar.monthrange(month.year, month.month)[1]
            )
            return min(self.today, last_day), month
        return self.today, self.today.replace(day=1)


AccountBalanceFormSet = forms.formset_factory(AccountBalanceForm, extra=0)
