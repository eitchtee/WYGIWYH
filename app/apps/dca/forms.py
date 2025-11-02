from apps.accounts.models import Account
from apps.common.fields.forms.dynamic_select import (
    DynamicModelChoiceField,
    DynamicModelMultipleChoiceField,
)
from apps.common.widgets.crispy.submit import NoClassSubmit
from apps.common.widgets.datepicker import AirDatePickerInput
from apps.common.widgets.decimal import ArbitraryDecimalDisplayNumberInput
from apps.common.widgets.tom_select import TomSelect, TransactionSelect
from apps.dca.models import DCAEntry, DCAStrategy
from apps.transactions.models import Transaction, TransactionCategory, TransactionTag
from crispy_bootstrap5.bootstrap5 import BS5Accordion, Switch
from crispy_forms.bootstrap import AccordionGroup, FormActions
from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Column, Layout, Row
from django import forms
from django.utils.translation import gettext_lazy as _


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
                Column("payment_currency"),
                Column("target_currency"),
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
    create_transaction = forms.BooleanField(
        label=_("Create transaction"), initial=False, required=False
    )

    from_account = forms.ModelChoiceField(
        queryset=Account.objects.filter(is_archived=False),
        label=_("From Account"),
        widget=TomSelect(clear_button=False, group_by="group"),
        required=False,
    )
    to_account = forms.ModelChoiceField(
        queryset=Account.objects.filter(is_archived=False),
        label=_("To Account"),
        widget=TomSelect(clear_button=False, group_by="group"),
        required=False,
    )

    from_category = DynamicModelChoiceField(
        create_field="name",
        model=TransactionCategory,
        required=False,
        label=_("Category"),
        queryset=TransactionCategory.objects.filter(active=True),
    )
    to_category = DynamicModelChoiceField(
        create_field="name",
        model=TransactionCategory,
        required=False,
        label=_("Category"),
        queryset=TransactionCategory.objects.filter(active=True),
    )

    from_tags = DynamicModelMultipleChoiceField(
        model=TransactionTag,
        to_field_name="name",
        create_field="name",
        required=False,
        label=_("Tags"),
        queryset=TransactionTag.objects.filter(active=True),
    )
    to_tags = DynamicModelMultipleChoiceField(
        model=TransactionTag,
        to_field_name="name",
        create_field="name",
        required=False,
        label=_("Tags"),
        queryset=TransactionTag.objects.filter(active=True),
    )

    expense_transaction = DynamicModelChoiceField(
        model=Transaction,
        to_field_name="id",
        label=_("Expense Transaction"),
        required=False,
        queryset=Transaction.objects.none(),
        widget=TransactionSelect(clear_button=True, income=False, expense=True),
        help_text=_("Type to search for a transaction to link to this entry"),
    )

    income_transaction = DynamicModelChoiceField(
        model=Transaction,
        to_field_name="id",
        label=_("Income Transaction"),
        required=False,
        queryset=Transaction.objects.none(),
        widget=TransactionSelect(clear_button=True, income=True, expense=False),
        help_text=_("Type to search for a transaction to link to this entry"),
    )

    class Meta:
        model = DCAEntry
        fields = [
            "date",
            "amount_paid",
            "amount_received",
            "notes",
            "expense_transaction",
            "income_transaction",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        strategy = kwargs.pop("strategy", None)
        super().__init__(*args, **kwargs)

        self.strategy = strategy if strategy else self.instance.strategy

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            "date",
            Row(
                Column("amount_paid"),
                Column("amount_received"),
            ),
            "notes",
            BS5Accordion(
                AccordionGroup(
                    _("Create transaction"),
                    Switch("create_transaction"),
                    Row(
                        Column(
                            Row(
                                Column(
                                    "from_account",
                                ),
                            ),
                            Row(
                                Column("from_category"),
                                Column("from_tags"),
                            ),
                        ),
                        css_class="p-1 mx-1 my-3 border rounded-3",
                    ),
                    Row(
                        Column(
                            Row(
                                Column(
                                    "to_account",
                                    css_class="form-group",
                                ),
                            ),
                            Row(
                                Column("to_category"),
                                Column("to_tags"),
                            ),
                        ),
                        css_class="p-1 mx-1 my-3 border rounded-3",
                    ),
                    active=False,
                ),
                AccordionGroup(
                    _("Link transaction"),
                    "income_transaction",
                    "expense_transaction",
                ),
                flush=False,
                always_open=False,
                css_class="mb-3",
            ),
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

        self.fields["amount_paid"].widget = ArbitraryDecimalDisplayNumberInput()
        self.fields["amount_received"].widget = ArbitraryDecimalDisplayNumberInput()
        self.fields["date"].widget = AirDatePickerInput(clear_button=False)

        expense_transaction = None
        income_transaction = None
        if self.instance and self.instance.pk:
            # Edit mode - get from instance
            expense_transaction = self.instance.expense_transaction
            income_transaction = self.instance.income_transaction
        elif self.data.get("expense_transaction"):
            # Form validation - get from submitted data
            try:
                expense_transaction = Transaction.objects.get(
                    id=self.data["expense_transaction"]
                )
                income_transaction = Transaction.objects.get(
                    id=self.data["income_transaction"]
                )
            except Transaction.DoesNotExist:
                pass

            # If we have a current transaction, ensure it's in the queryset
        if income_transaction:
            self.fields["income_transaction"].queryset = Transaction.objects.filter(
                id=income_transaction.id
            )
        if expense_transaction:
            self.fields["expense_transaction"].queryset = Transaction.objects.filter(
                id=expense_transaction.id
            )

        self.fields["from_account"].queryset = Account.objects.filter(
            is_archived=False,
        )

        self.fields["from_category"].queryset = TransactionCategory.objects.filter(
            active=True
        )
        self.fields["from_tags"].queryset = TransactionTag.objects.filter(active=True)

        self.fields["to_account"].queryset = Account.objects.filter(
            is_archived=False,
        )

        self.fields["to_category"].queryset = TransactionCategory.objects.filter(
            active=True
        )
        self.fields["to_tags"].queryset = TransactionTag.objects.filter(active=True)

    def clean(self):
        cleaned_data = super().clean()

        if cleaned_data.get("create_transaction"):
            from_account = cleaned_data.get("from_account")
            to_account = cleaned_data.get("to_account")

            if not from_account and not to_account:
                raise forms.ValidationError(
                    {
                        "from_account": _("You must provide an account."),
                        "to_account": _("You must provide an account."),
                    }
                )
            elif not from_account and to_account:
                raise forms.ValidationError(
                    {"from_account": _("You must provide an account.")}
                )
            elif not to_account and from_account:
                raise forms.ValidationError(
                    {"to_account": _("You must provide an account.")}
                )

            if from_account == to_account:
                raise forms.ValidationError(
                    _("From and To accounts must be different.")
                )

        return cleaned_data

    def save(self, **kwargs):
        instance = super().save(commit=False)

        if self.cleaned_data.get("create_transaction"):
            from_account = self.cleaned_data["from_account"]
            to_account = self.cleaned_data["to_account"]
            from_amount = instance.amount_paid
            to_amount = instance.amount_received
            date = instance.date
            description = _("DCA for %(strategy_name)s") % {
                "strategy_name": self.strategy.name
            }
            from_category = self.cleaned_data.get("from_category")
            to_category = self.cleaned_data.get("to_category")
            notes = self.cleaned_data.get("notes")

            # Create "From" transaction
            from_transaction = Transaction.objects.create(
                account=from_account,
                type=Transaction.Type.EXPENSE,
                is_paid=True,
                date=date,
                amount=from_amount,
                description=description,
                category=from_category,
                notes=notes,
            )
            from_transaction.tags.set(self.cleaned_data.get("from_tags", []))

            # Create "To" transaction
            to_transaction = Transaction.objects.create(
                account=to_account,
                type=Transaction.Type.INCOME,
                is_paid=True,
                date=date,
                amount=to_amount,
                description=description,
                category=to_category,
                notes=notes,
            )
            to_transaction.tags.set(self.cleaned_data.get("to_tags", []))

            instance.expense_transaction = from_transaction
            instance.income_transaction = to_transaction
        else:
            if instance.expense_transaction:
                instance.expense_transaction.amount = instance.amount_paid
                instance.expense_transaction.save()
            if instance.income_transaction:
                instance.income_transaction.amount = instance.amount_received
                instance.income_transaction.save()

        instance.strategy = self.strategy
        instance.save()

        return instance
