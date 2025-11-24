from apps.accounts.models import Account, AccountGroup
from apps.common.fields.forms.dynamic_select import (
    DynamicModelChoiceField,
    DynamicModelMultipleChoiceField,
)
from apps.common.widgets.crispy.daisyui import Switch
from apps.common.widgets.crispy.submit import NoClassSubmit
from apps.common.widgets.decimal import ArbitraryDecimalDisplayNumberInput
from apps.common.widgets.tom_select import TomSelect
from apps.currencies.models import Currency
from apps.transactions.models import TransactionCategory, TransactionTag
from crispy_forms.bootstrap import FormActions
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Column, Field, Layout, Row
from django import forms
from django.db.models import Q
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


AccountBalanceFormSet = forms.formset_factory(AccountBalanceForm, extra=0)
