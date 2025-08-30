from crispy_bootstrap5.bootstrap5 import Switch
from crispy_forms.bootstrap import FormActions
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field, Column, Row
from django import forms
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import Account
from apps.accounts.models import AccountGroup
from apps.common.fields.forms.dynamic_select import (
    DynamicModelMultipleChoiceField,
    DynamicModelChoiceField,
)
from apps.common.widgets.crispy.submit import NoClassSubmit
from apps.common.widgets.tom_select import TomSelect
from apps.transactions.models import TransactionCategory, TransactionTag
from apps.common.widgets.decimal import ArbitraryDecimalDisplayNumberInput
from apps.currencies.models import Currency


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
            self.fields["currency"].queryset = Currency.objects.filter(
                Q(is_archived=False) | Q(accounts=self.instance.id),
            )

            self.fields["exchange_currency"].queryset = Currency.objects.filter(
                Q(is_archived=False) | Q(accounts=self.instance.id)
            )

        else:
            self.fields["currency"].queryset = Currency.objects.filter(
                Q(is_archived=False),
            )

            self.fields["exchange_currency"].queryset = Currency.objects.filter(
                Q(is_archived=False)
            )

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
                Column("category", css_class="form-group col-md-6 mb-0"),
                Column("tags", css_class="form-group col-md-6 mb-0"),
                css_class="form-row",
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
