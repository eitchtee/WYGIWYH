from crispy_bootstrap5.bootstrap5 import Switch
from crispy_forms.bootstrap import FormActions
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Row, Column, Field, Fieldset
from dateutil.relativedelta import relativedelta
from django import forms
from django.db import transaction
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import Account
from apps.common.fields.forms.dynamic_select import (
    DynamicModelChoiceField,
    DynamicModelMultipleChoiceField,
)
from apps.common.widgets.crispy.submit import NoClassSubmit
from apps.common.widgets.tom_select import TomSelect, TomSelectMultiple
from apps.transactions.models import (
    Transaction,
    TransactionCategory,
    TransactionTag,
    InstallmentPlan,
)
from apps.transactions.widgets import (
    ArbitraryDecimalDisplayNumberInput,
    MonthYearWidget,
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
        # labels = {
        #     "tags": mark_safe('<i class="fa-solid fa-hashtag me-1"></i>' + _("Tags")),
        #     "category": mark_safe(
        #         '<i class="fa-solid fa-icons me-1"></i>' + _("Category")
        #     ),
        #     "notes": mark_safe(
        #         '<i class="fa-solid fa-align-justify me-1"></i>' + _("Notes")
        #     ),
        #     "amount": mark_safe('<i class="fa-solid fa-coins me-1"></i>' + _("Amount")),
        #     "description": mark_safe(
        #         '<i class="fa-solid fa-quote-left me-1"></i>' + _("Name")
        #     ),
        # }

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
    from_account = forms.ModelChoiceField(
        queryset=Account.objects.all(),
        label="From Account",
        widget=TomSelect(),
    )
    to_account = forms.ModelChoiceField(
        queryset=Account.objects.all(),
        label="To Account",
        widget=TomSelect(),
    )

    from_amount = forms.DecimalField(
        max_digits=42,
        decimal_places=30,
        label="From Amount",
    )
    to_amount = forms.DecimalField(
        max_digits=42,
        decimal_places=30,
        label="To Amount",
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
        label="Date", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
    )
    reference_date = forms.CharField(label="Reference Date", widget=MonthYearWidget())
    description = forms.CharField(max_length=500, label="Description")

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
                    "submit", _("Tranfer"), css_class="btn btn-outline-primary w-100"
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


class InstallmentPlanForm(forms.Form):
    type = forms.ChoiceField(choices=Transaction.Type.choices)
    account = forms.ModelChoiceField(
        queryset=Account.objects.all(),
        label=_("Account"),
        widget=TomSelect(),
    )
    start_date = forms.DateField(
        label=_("Start Date"),
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    description = forms.CharField(max_length=500, label=_("Description"))
    number_of_installments = forms.IntegerField(
        min_value=1, label=_("Number of Installments")
    )
    recurrence = forms.ChoiceField(
        choices=(
            ("yearly", _("Yearly")),
            ("monthly", _("Monthly")),
            ("weekly", _("Weekly")),
            ("daily", _("Daily")),
        ),
        initial="monthly",
        widget=TomSelect(clear_button=False),
    )
    installment_amount = forms.DecimalField(
        max_digits=42,
        decimal_places=30,
        required=True,
        label=_("Installment Amount"),
    )
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
                Column("start_date", css_class="form-group col-md-4 mb-0"),
                Column("number_of_installments", css_class="form-group col-md-4 mb-0"),
                Column("recurrence", css_class="form-group col-md-4 mb-0"),
                css_class="form-row",
            ),
            "installment_amount",
            Row(
                Column("category", css_class="form-group col-md-6 mb-0"),
                Column("tags", css_class="form-group col-md-6 mb-0"),
                css_class="form-row",
            ),
            FormActions(
                NoClassSubmit(
                    "submit", _("Add"), css_class="btn btn-outline-primary w-100"
                ),
            ),
        )

        self.fields["installment_amount"].widget = ArbitraryDecimalDisplayNumberInput()

    def save(self):
        number_of_installments = self.cleaned_data["number_of_installments"]
        transaction_type = self.cleaned_data["type"]
        start_date = self.cleaned_data["start_date"]
        recurrence = self.cleaned_data["recurrence"]
        account = self.cleaned_data["account"]
        description = self.cleaned_data["description"]
        installment_amount = self.cleaned_data["installment_amount"]
        category = self.cleaned_data["category"]

        with transaction.atomic():
            installment_plan = InstallmentPlan.objects.create(
                account=account,
                description=description,
                number_of_installments=number_of_installments,
            )

            with transaction.atomic():
                for i in range(number_of_installments):
                    if recurrence == "yearly":
                        delta = relativedelta(years=i)
                    elif recurrence == "monthly":
                        delta = relativedelta(months=i)
                    elif recurrence == "weekly":
                        delta = relativedelta(weeks=i)
                    elif recurrence == "daily":
                        delta = relativedelta(days=i)

                    transaction_date = start_date + delta
                    new_transaction = Transaction.objects.create(
                        account=account,
                        type=transaction_type,
                        date=transaction_date,
                        reference_date=transaction_date.replace(day=1),
                        amount=installment_amount,
                        description=description,
                        notes=f"{i + 1}/{number_of_installments}",
                        category=category,
                        installment_plan=installment_plan,
                    )

                    new_transaction.tags.set(self.cleaned_data.get("tags", []))

        return installment_plan


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
