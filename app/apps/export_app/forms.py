from crispy_forms.bootstrap import FormActions
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, HTML
from django import forms
from django.utils.translation import gettext_lazy as _

from apps.common.widgets.crispy.submit import NoClassSubmit


class ExportForm(forms.Form):
    users = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(),
        label=_("Users"),
        initial=True,
    )
    accounts = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(),
        label=_("Accounts"),
        initial=True,
    )
    currencies = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(),
        label=_("Currencies"),
        initial=True,
    )
    transactions = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(),
        label=_("Transactions"),
        initial=True,
    )
    categories = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(),
        label=_("Categories"),
        initial=True,
    )
    tags = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(),
        label=_("Tags"),
        initial=False,
    )
    entities = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(),
        label=_("Entities"),
        initial=False,
    )
    recurring_transactions = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(),
        label=_("Recurring Transactions"),
        initial=True,
    )
    installment_plans = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(),
        label=_("Installment Plans"),
        initial=True,
    )
    exchange_rates = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(),
        label=_("Exchange Rates"),
        initial=False,
    )
    exchange_rates_services = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(),
        label=_("Automatic Exchange Rates"),
        initial=False,
    )
    rules = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(),
        label=_("Rules"),
        initial=True,
    )
    dca = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(),
        label=_("DCA"),
        initial=False,
    )
    import_profiles = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(),
        label=_("Import Profiles"),
        initial=True,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = "post"
        self.helper.layout = Layout(
            "users",
            "accounts",
            "currencies",
            "transactions",
            "categories",
            "entities",
            "tags",
            "installment_plans",
            "recurring_transactions",
            "exchange_rates_services",
            "exchange_rates",
            "rules",
            "dca",
            "import_profiles",
            FormActions(
                NoClassSubmit(
                    "submit", _("Export"), css_class="btn btn-outline-primary w-100"
                ),
            ),
        )


class RestoreForm(forms.Form):
    zip_file = forms.FileField(
        required=False,
        help_text=_("Import a ZIP file exported from WYGIWYH"),
        label=_("ZIP File"),
    )
    users = forms.FileField(required=False, label=_("Users"))
    accounts = forms.FileField(required=False, label=_("Accounts"))
    currencies = forms.FileField(required=False, label=_("Currencies"))
    transactions_categories = forms.FileField(required=False, label=_("Categories"))
    transactions_tags = forms.FileField(required=False, label=_("Tags"))
    transactions_entities = forms.FileField(required=False, label=_("Entities"))
    transactions = forms.FileField(required=False, label=_("Transactions"))
    installment_plans = forms.FileField(required=False, label=_("Installment Plans"))
    recurring_transactions = forms.FileField(
        required=False, label=_("Recurring Transactions")
    )
    automatic_exchange_rates = forms.FileField(
        required=False, label=_("Automatic Exchange Rates")
    )
    exchange_rates = forms.FileField(required=False, label=_("Exchange Rates"))
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

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = "post"
        self.helper.layout = Layout(
            "zip_file",
            HTML("<hr />"),
            "users",
            "accounts",
            "currencies",
            "transactions",
            "transactions_categories",
            "transactions_entities",
            "transactions_tags",
            "installment_plans",
            "recurring_transactions",
            "automatic_exchange_rates",
            "exchange_rates",
            "transaction_rules",
            "transaction_rules_actions",
            "transaction_rules_update_or_create",
            "dca_strategies",
            "dca_entries",
            "import_profiles",
            FormActions(
                NoClassSubmit(
                    "submit", _("Restore"), css_class="btn btn-outline-primary w-100"
                ),
            ),
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
