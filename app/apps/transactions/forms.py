from crispy_bootstrap5.bootstrap5 import Switch
from django import forms
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit, Row, Column, Div, Field, Hidden

from .models import Transaction
from apps.transactions.widgets import ArbitraryDecimalDisplayNumberInput


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
            Submit("submit", "Save", css_class="btn btn-primary"),
            Submit("submit", "Save", css_class="btn btn-warning"),
        )
        if self.instance and self.instance.pk:
            decimal_places = self.instance.account.currency.decimal_places
            self.fields["amount"].widget = ArbitraryDecimalDisplayNumberInput(
                decimal_places=decimal_places
            )
