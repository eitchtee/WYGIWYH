from crispy_bootstrap5.bootstrap5 import Switch
from django import forms
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit, Row, Column, Div, Field, Hidden

from apps.accounts.models import Account
from .models import Transaction, TransactionCategory, TransactionTag
from apps.transactions.widgets import (
    ArbitraryDecimalDisplayNumberInput,
    MonthYearWidget,
)


class TransactionForm(forms.ModelForm):
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
        }
        labels = {
            "tags": mark_safe('<i class="fa-solid fa-hashtag me-1"></i>' + _("Tags")),
            "category": mark_safe(
                '<i class="fa-solid fa-icons me-1"></i>' + _("Category")
            ),
            "notes": mark_safe(
                '<i class="fa-solid fa-align-justify me-1"></i>' + _("Notes")
            ),
            "amount": mark_safe('<i class="fa-solid fa-coins me-1"></i>' + _("Amount")),
            "description": mark_safe(
                '<i class="fa-solid fa-quote-left me-1"></i>' + _("Name")
            ),
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
            "amount",
            Field("category", css_class="select"),
            Field("tags", css_class="multiselect", size=1),
            "notes",
            Submit("submit", "Save", css_class="btn btn-warning"),
        )
        if self.instance and self.instance.pk:
            decimal_places = self.instance.account.currency.decimal_places
            self.fields["amount"].widget = ArbitraryDecimalDisplayNumberInput(
                decimal_places=decimal_places
            )


class TransferForm(forms.Form):
    from_account = forms.ModelChoiceField(
        queryset=Account.objects.all(), label="From Account"
    )
    to_account = forms.ModelChoiceField(
        queryset=Account.objects.all(), label="To Account"
    )

    from_amount = forms.DecimalField(
        max_digits=42, decimal_places=30, label="From Amount", step_size=1
    )
    to_amount = forms.DecimalField(
        max_digits=42, decimal_places=30, label="To Amount", required=False, step_size=1
    )

    from_category = forms.ModelChoiceField(
        queryset=TransactionCategory.objects.all(),
        required=False,
        label="From Category",
    )
    to_category = forms.ModelChoiceField(
        queryset=TransactionCategory.objects.all(), required=False, label="To Category"
    )

    from_tags = forms.ModelMultipleChoiceField(
        queryset=TransactionTag.objects.all(), required=False, label="From Tags"
    )
    to_tags = forms.ModelMultipleChoiceField(
        queryset=TransactionTag.objects.all(), required=False, label="To Tags"
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
                Column("date", css_class="form-group col-md-6 mb-0"),
                Column("reference_date", css_class="form-group col-md-6 mb-0"),
                css_class="form-row",
            ),
            "description",
            Row(
                Column(
                    Row(
                        Column("from_account", css_class="form-group col-md-6 mb-0"),
                        Column("from_amount", css_class="form-group col-md-6 mb-0"),
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
                        Column("to_account", css_class="form-group col-md-6 mb-0"),
                        Column("to_amount", css_class="form-group col-md-6 mb-0"),
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
            Submit("submit", "Save", css_class="btn btn-primary"),
        )

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

        # Create "From" transaction
        from_transaction = Transaction.objects.create(
            account=from_account,
            type=Transaction.Type.EXPENSE,
            is_paid=True,
            date=date,
            reference_date=reference_date,
            amount=from_amount,
            description=f"Transfer to {to_account}: {description}",
            category=self.cleaned_data.get("from_category"),
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
            description=f"Transfer from {from_account}: {description}",
            category=self.cleaned_data.get("to_category"),
        )
        to_transaction.tags.set(self.cleaned_data.get("to_tags", []))

        return from_transaction, to_transaction
