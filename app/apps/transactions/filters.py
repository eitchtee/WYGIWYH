import django_filters
from crispy_bootstrap5.bootstrap5 import Switch
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field
from django import forms
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import Account
from apps.transactions.models import Transaction
from apps.transactions.models import TransactionCategory
from apps.transactions.models import TransactionTag
from apps.common.widgets.tom_select import TomSelect, TomSelectMultiple

SITUACAO_CHOICES = (
    ("1", _("Paid")),
    ("0", _("Projected")),
)


def content_filter(queryset, name, value):
    queryset = queryset.filter(
        Q(description__icontains=value) | Q(notes__icontains=value)
    )
    return queryset


class TransactionsFilter(django_filters.FilterSet):
    description = django_filters.CharFilter(
        label=_("Content"),
        method=content_filter,
        widget=forms.TextInput(attrs={"type": "search"}),
    )
    type = django_filters.MultipleChoiceFilter(
        choices=Transaction.Type.choices,
        label=_("Transaction Type"),
    )
    account = django_filters.ModelMultipleChoiceFilter(
        field_name="account__name",
        queryset=Account.objects.all(),
        to_field_name="name",
        label=_("Accounts"),
        widget=TomSelectMultiple(checkboxes=True, remove_button=True),
    )
    category = django_filters.ModelMultipleChoiceFilter(
        field_name="category__name",
        queryset=TransactionCategory.objects.all(),
        to_field_name="name",
        label=_("Categories"),
        widget=TomSelectMultiple(checkboxes=True, remove_button=True),
    )
    tags = django_filters.ModelMultipleChoiceFilter(
        field_name="tags__name",
        queryset=TransactionTag.objects.all(),
        to_field_name="name",
        label=_("Tags"),
        widget=TomSelectMultiple(checkboxes=True, remove_button=True),
    )
    is_paid = django_filters.MultipleChoiceFilter(
        choices=SITUACAO_CHOICES,
        field_name="is_paid",
    )

    class Meta:
        model = Transaction
        fields = [
            "description",
            "type",
            "account",
            "is_paid",
            "category",
            "tags",
        ]

    def __init__(self, data=None, *args, **kwargs):
        # if filterset is bound, use initial values as defaults
        if data is not None:
            # get a mutable copy of the QueryDict
            data = data.copy()

            # # set type to all if it isn't set
            if data.get("type") is None:
                data.setlist("type", ["IN", "EX"])

            if data.get("is_paid") is None:
                data.setlist("is_paid", ["1", "0"])

        super().__init__(data, *args, **kwargs)

        self.form.helper = FormHelper()
        self.form.helper.form_tag = False
        self.form.helper.form_method = "GET"
        self.form.helper.disable_csrf = True
        self.form.helper.layout = Layout(
            Field(
                "type",
                template="transactions/widgets/transaction_type_filter_buttons.html",
            ),
            Field(
                "is_paid",
                template="transactions/widgets/transaction_type_filter_buttons.html",
            ),
            Field("description"),
            Field("account", size=1),
            Field("category", size=1),
            Field("tags", size=1),
        )
