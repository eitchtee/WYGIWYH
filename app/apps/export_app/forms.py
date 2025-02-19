from crispy_forms.bootstrap import FormActions
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout
from django import forms
from django.utils.translation import gettext_lazy as _

from apps.common.widgets.crispy.submit import NoClassSubmit


class ExportForm(forms.Form):
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.form_method = "post"
        self.helper.layout = Layout(
            "accounts",
            "currencies",
            "transactions",
            "categories",
            "entities",
            "tags",
            "exchange_rates_services",
            "exchange_rates",
            FormActions(
                NoClassSubmit(
                    "submit", _("Export"), css_class="btn btn-outline-primary w-100"
                ),
            ),
        )
