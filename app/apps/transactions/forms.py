from crispy_bootstrap5.bootstrap5 import Switch
from crispy_forms.bootstrap import FormActions
from crispy_forms.helper import FormHelper
from crispy_forms.layout import (
    Layout,
    Row,
    Column,
    Field,
)
from django import forms
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import Account
from apps.common.fields.forms.dynamic_select import (
    DynamicModelChoiceField,
    DynamicModelMultipleChoiceField,
)
from apps.common.fields.forms.grouped_select import GroupedModelChoiceField
from apps.common.fields.month_year import MonthYearFormField
from apps.common.widgets.crispy.submit import NoClassSubmit
from apps.common.widgets.decimal import ArbitraryDecimalDisplayNumberInput
from apps.common.widgets.tom_select import TomSelect
from apps.transactions.models import (
    Transaction,
    TransactionCategory,
    TransactionTag,
    InstallmentPlan,
    RecurringTransaction,
)


class TransactionForm(forms.ModelForm):
    category = DynamicModelChoiceField(
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
    reference_date = MonthYearFormField(label=_("Reference Date"), required=False)
    account = GroupedModelChoiceField(
        queryset=Account.objects.all(),
        group_by="group",
    )

    class Meta:
        model = Transaction
        fields = [
            "account",
            "type",
            "is_paid",
            "date",
            "reference_date",
            "amount",
            "description",
            "notes",
            "category",
            "tags",
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "account": TomSelect(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = "post"
        self.helper.layout = Layout(
            Field(
                "type",
                template="transactions/widgets/income_expense_toggle_buttons.html",
            ),
            Switch("is_paid"),
            "account",
            Row(
                Column("date", css_class="form-group col-md-6 mb-0"),
                Column("reference_date", css_class="form-group col-md-6 mb-0"),
                css_class="form-row",
            ),
            "description",
            Field("amount", inputmode="decimal"),
            Row(
                Column("category", css_class="form-group col-md-6 mb-0"),
                Column("tags", css_class="form-group col-md-6 mb-0"),
                css_class="form-row",
            ),
            "notes",
        )

        self.fields["reference_date"].required = False

        if self.instance and self.instance.pk:
            decimal_places = self.instance.account.currency.decimal_places
            self.fields["amount"].widget = ArbitraryDecimalDisplayNumberInput(
                decimal_places=decimal_places
            )
            self.helper.layout.append(
                FormActions(
                    NoClassSubmit(
                        "submit", _("Update"), css_class="btn btn-outline-primary w-100"
                    ),
                ),
            )
        else:
            self.fields["amount"].widget = ArbitraryDecimalDisplayNumberInput()
            self.helper.layout.append(
                FormActions(
                    NoClassSubmit(
                        "submit", _("Add"), css_class="btn btn-outline-primary w-100"
                    ),
                ),
            )

    def clean(self):
        cleaned_data = super().clean()
        date = cleaned_data.get("date")
        reference_date = cleaned_data.get("reference_date")

        if date and not reference_date:
            cleaned_data["reference_date"] = date.replace(day=1)

        return cleaned_data


class TransferForm(forms.Form):
    from_account = GroupedModelChoiceField(
        queryset=Account.objects.all(),
        group_by="group",
        label=_("From Account"),
        widget=TomSelect(),
    )
    to_account = GroupedModelChoiceField(
        queryset=Account.objects.all(),
        group_by="group",
        label=_("To Account"),
        widget=TomSelect(),
    )

    from_amount = forms.DecimalField(
        max_digits=42,
        decimal_places=30,
        label=_("From Amount"),
    )
    to_amount = forms.DecimalField(
        max_digits=42,
        decimal_places=30,
        label=_("To Amount"),
        required=False,
    )

    from_category = DynamicModelChoiceField(
        model=TransactionCategory,
        required=False,
        label=_("Category"),
    )
    to_category = DynamicModelChoiceField(
        model=TransactionCategory,
        required=False,
        label=_("Category"),
    )

    from_tags = DynamicModelMultipleChoiceField(
        model=TransactionTag,
        to_field_name="name",
        create_field="name",
        required=False,
        label=_("Tags"),
    )
    to_tags = DynamicModelMultipleChoiceField(
        model=TransactionTag,
        to_field_name="name",
        create_field="name",
        required=False,
        label=_("Tags"),
    )

    date = forms.DateField(
        label=_("Date"),
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    reference_date = MonthYearFormField(label=_("Reference Date"), required=False)
    description = forms.CharField(max_length=500, label=_("Description"))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = "post"

        self.helper.layout = Layout(
            Row(
                Column(Field("date"), css_class="form-group col-md-6 mb-0"),
                Column(
                    Field("reference_date"),
                    css_class="form-group col-md-6 mb-0",
                ),
                css_class="form-row",
            ),
            Field("description"),
            Row(
                Column(
                    Row(
                        Column(
                            "from_account",
                            css_class="form-group col-md-6 mb-0",
                        ),
                        Column(
                            Field("from_amount"),
                            css_class="form-group col-md-6 mb-0",
                        ),
                        css_class="form-row",
                    ),
                    Row(
                        Column("from_category", css_class="form-group col-md-6 mb-0"),
                        Column("from_tags", css_class="form-group col-md-6 mb-0"),
                        css_class="form-row",
                    ),
                ),
                css_class="p-1 mx-1 my-3 border rounded-3",
            ),
            Row(
                Column(
                    Row(
                        Column(
                            "to_account",
                            css_class="form-group col-md-6 mb-0",
                        ),
                        Column(
                            Field("to_amount"),
                            css_class="form-group col-md-6 mb-0",
                        ),
                        css_class="form-row",
                    ),
                    Row(
                        Column("to_category", css_class="form-group col-md-6 mb-0"),
                        Column("to_tags", css_class="form-group col-md-6 mb-0"),
                        css_class="form-row",
                    ),
                ),
                css_class="p-1 mx-1 my-3 border rounded-3",
            ),
            FormActions(
                NoClassSubmit(
                    "submit", _("Transfer"), css_class="btn btn-outline-primary w-100"
                ),
            ),
        )

        self.fields["from_amount"].widget = ArbitraryDecimalDisplayNumberInput()

        self.fields["to_amount"].widget = ArbitraryDecimalDisplayNumberInput()

    def clean(self):
        cleaned_data = super().clean()
        from_account = cleaned_data.get("from_account")
        to_account = cleaned_data.get("to_account")

        if from_account == to_account:
            raise forms.ValidationError("From and To accounts must be different.")

        return cleaned_data

    def save(self):
        from_account = self.cleaned_data["from_account"]
        to_account = self.cleaned_data["to_account"]
        from_amount = self.cleaned_data["from_amount"]
        to_amount = self.cleaned_data["to_amount"] or from_amount
        date = self.cleaned_data["date"]
        reference_date = self.cleaned_data["reference_date"]
        description = self.cleaned_data["description"]
        from_category = self.cleaned_data.get("from_category")
        to_category = self.cleaned_data.get("to_category")

        # Create "From" transaction
        from_transaction = Transaction.objects.create(
            account=from_account,
            type=Transaction.Type.EXPENSE,
            is_paid=True,
            date=date,
            reference_date=reference_date,
            amount=from_amount,
            description=description,
            category=from_category,
        )
        from_transaction.tags.set(self.cleaned_data.get("from_tags", []))

        # Create "To" transaction
        to_transaction = Transaction.objects.create(
            account=to_account,
            type=Transaction.Type.INCOME,
            is_paid=True,
            date=date,
            reference_date=reference_date,
            amount=to_amount,
            description=description,
            category=to_category,
        )
        to_transaction.tags.set(self.cleaned_data.get("to_tags", []))

        return from_transaction, to_transaction


class InstallmentPlanForm(forms.ModelForm):
    account = GroupedModelChoiceField(
        queryset=Account.objects.all(),
        group_by="group",
        widget=TomSelect(),
    )
    tags = DynamicModelMultipleChoiceField(
        model=TransactionTag,
        to_field_name="name",
        create_field="name",
        required=False,
        label=_("Tags"),
    )
    category = DynamicModelChoiceField(
        model=TransactionCategory,
        required=False,
        label=_("Category"),
    )
    type = forms.ChoiceField(choices=Transaction.Type.choices)
    reference_date = MonthYearFormField(label=_("Reference Date"), required=False)

    class Meta:
        model = InstallmentPlan
        fields = [
            "type",
            "account",
            "start_date",
            "reference_date",
            "description",
            "number_of_installments",
            "recurrence",
            "installment_amount",
            "category",
            "tags",
            "installment_start",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "account": TomSelect(),
            "recurrence": TomSelect(clear_button=False),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = "post"

        self.helper.layout = Layout(
            Field(
                "type",
                template="transactions/widgets/income_expense_toggle_buttons.html",
            ),
            "account",
            "description",
            Row(
                Column("number_of_installments", css_class="form-group col-md-6 mb-0"),
                Column("installment_start", css_class="form-group col-md-6 mb-0"),
                css_class="form-row",
            ),
            "recurrence",
            Row(
                Column("start_date", css_class="form-group col-md-6 mb-0"),
                Column("reference_date", css_class="form-group col-md-6 mb-0"),
                css_class="form-row",
            ),
            "installment_amount",
            Row(
                Column("category", css_class="form-group col-md-6 mb-0"),
                Column("tags", css_class="form-group col-md-6 mb-0"),
                css_class="form-row",
            ),
        )

        self.fields["installment_amount"].widget = ArbitraryDecimalDisplayNumberInput()

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

    def save(self, **kwargs):
        is_new = not self.instance.id

        instance = super().save(**kwargs)
        if is_new:
            instance.create_transactions()
        else:
            instance.update_transactions()

        return instance


class TransactionTagForm(forms.ModelForm):
    class Meta:
        model = TransactionTag
        fields = ["name"]
        labels = {"name": _("Tag name")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = "post"
        self.helper.layout = Layout(Field("name", css_class="mb-3"))

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


class TransactionCategoryForm(forms.ModelForm):
    class Meta:
        model = TransactionCategory
        fields = ["name", "mute"]
        labels = {"name": _("Category name")}
        help_texts = {
            "mute": _("Muted categories won't count towards your monthly total")
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = "post"
        self.helper.layout = Layout(Field("name", css_class="mb-3"), Switch("mute"))

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


class RecurringTransactionForm(forms.ModelForm):
    account = GroupedModelChoiceField(
        queryset=Account.objects.all(),
        group_by="group",
        widget=TomSelect(),
    )
    tags = DynamicModelMultipleChoiceField(
        model=TransactionTag,
        to_field_name="name",
        create_field="name",
        required=False,
        label=_("Tags"),
    )
    category = DynamicModelChoiceField(
        model=TransactionCategory,
        required=False,
        label=_("Category"),
    )
    type = forms.ChoiceField(choices=Transaction.Type.choices)
    reference_date = MonthYearFormField(label=_("Reference Date"), required=False)

    class Meta:
        model = RecurringTransaction
        fields = [
            "account",
            "type",
            "amount",
            "description",
            "category",
            "tags",
            "start_date",
            "reference_date",
            "end_date",
            "recurrence_type",
            "recurrence_interval",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "end_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "account": TomSelect(clear_button=False),
            "recurrence_type": TomSelect(clear_button=False),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.form_tag = False

        self.helper.layout = Layout(
            Field(
                "type",
                template="transactions/widgets/income_expense_toggle_buttons.html",
            ),
            "account",
            "description",
            "amount",
            Row(
                Column("category", css_class="form-group col-md-6 mb-0"),
                Column("tags", css_class="form-group col-md-6 mb-0"),
                css_class="form-row",
            ),
            Row(
                Column("start_date", css_class="form-group col-md-6 mb-0"),
                Column("reference_date", css_class="form-group col-md-6 mb-0"),
                css_class="form-row",
            ),
            Row(
                Column("recurrence_interval", css_class="form-group col-md-4 mb-0"),
                Column("recurrence_type", css_class="form-group col-md-4 mb-0"),
                Column("end_date", css_class="form-group col-md-4 mb-0"),
                css_class="form-row",
            ),
        )

        self.fields["amount"].widget = ArbitraryDecimalDisplayNumberInput()

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

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")

        if start_date and end_date and start_date > end_date:
            raise forms.ValidationError("End date should be after the start date.")

        return cleaned_data

    def save(self, **kwargs):
        is_new = not self.instance.id

        instance = super().save(**kwargs)
        if is_new:
            instance.create_upcoming_transactions()

        return instance
