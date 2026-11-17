from django import forms
from django.utils.translation import gettext_lazy as _


class ExportForm(forms.Form):
    # Rendered by export_app/fragments/export.html, in declaration order
    users = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "checkbox"}),
        label=_("Users"),
        initial=True,
    )
    accounts = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "checkbox"}),
        label=_("Accounts"),
        initial=True,
    )
    currencies = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "checkbox"}),
        label=_("Currencies"),
        initial=True,
    )
    transactions = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "checkbox"}),
        label=_("Transactions"),
        initial=True,
    )
    categories = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "checkbox"}),
        label=_("Categories"),
        initial=True,
    )
    entities = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "checkbox"}),
        label=_("Entities"),
        initial=False,
    )
    tags = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "checkbox"}),
        label=_("Tags"),
        initial=False,
    )
    installment_plans = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "checkbox"}),
        label=_("Installment Plans"),
        initial=True,
    )
    recurring_transactions = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "checkbox"}),
        label=_("Recurring Transactions"),
        initial=True,
    )
    quick_transactions = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "checkbox"}),
        label=_("Quick Transactions"),
        initial=True,
    )
    exchange_rates_services = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "checkbox"}),
        label=_("Automatic Exchange Rates"),
        initial=False,
    )
    exchange_rates = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "checkbox"}),
        label=_("Exchange Rates"),
        initial=False,
    )
    bank_sync = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "checkbox"}),
        label=_("Bank Sync"),
        help_text=_("Includes the providers' API keys"),
        initial=False,
    )
    rules = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "checkbox"}),
        label=_("Rules"),
        initial=True,
    )
    dca = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "checkbox"}),
        label=_("DCA"),
        initial=False,
    )
    import_profiles = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "checkbox"}),
        label=_("Import Profiles"),
        initial=True,
    )


class RestoreForm(forms.Form):
    zip_file = forms.FileField(
        required=False,
        help_text=_("Import a ZIP file exported from WYGIWYH"),
        label=_("ZIP File"),
    )
    users = forms.FileField(required=False, label=_("Users"))
    accounts = forms.FileField(required=False, label=_("Accounts"))
    investment_classes = forms.FileField(required=False, label=_("Asset classes"))
    currencies = forms.FileField(required=False, label=_("Currencies"))
    transactions_categories = forms.FileField(required=False, label=_("Categories"))
    transactions_tags = forms.FileField(required=False, label=_("Tags"))
    transactions_entities = forms.FileField(required=False, label=_("Entities"))
    transactions = forms.FileField(required=False, label=_("Transactions"))
    sub_transactions = forms.FileField(required=False, label=_("Sub-transactions"))
    installment_plans = forms.FileField(required=False, label=_("Installment Plans"))
    recurring_transactions = forms.FileField(
        required=False, label=_("Recurring Transactions")
    )
    quick_transactions = forms.FileField(required=False, label=_("Quick Transactions"))
    automatic_exchange_rates = forms.FileField(
        required=False, label=_("Automatic Exchange Rates")
    )
    exchange_rates = forms.FileField(required=False, label=_("Exchange Rates"))
    bank_sync_services = forms.FileField(
        required=False, label=_("Bank Sync Services")
    )
    bank_sync_accounts = forms.FileField(
        required=False, label=_("Bank Sync Accounts")
    )
    transaction_rules = forms.FileField(required=False, label=_("Transaction rules"))
    transaction_rules_actions = forms.FileField(
        required=False, label=_("Edit transaction action")
    )
    transaction_rules_update_or_create = forms.FileField(
        required=False, label=_("Update or create transaction actions")
    )
    dca_strategies = forms.FileField(required=False, label=_("DCA Strategies"))
    dca_entries = forms.FileField(required=False, label=_("DCA Entries"))
    import_profiles = forms.FileField(required=False, label=_("Import Profiles"))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Rendered by export_app/fragments/restore.html
        for name, field in self.fields.items():
            field.widget.attrs.update(
                {"class": "file-input w-full", "accept": ".zip" if name == "zip_file" else ".csv"}
            )

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get("zip_file") and not any(
            cleaned_data.get(field) for field in self.fields if field != "zip_file"
        ):
            raise forms.ValidationError(
                _("Please upload either a ZIP file or at least one CSV file")
            )
        return cleaned_data
