import django_filters
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field, Row, Column
from django import forms
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django_filters import Filter

from apps.accounts.models import Account
from apps.transactions.models import Transaction
from apps.transactions.models import TransactionCategory
from apps.transactions.models import TransactionTag
from apps.common.widgets.tom_select import TomSelectMultiple
from apps.common.fields.month_year import MonthYearFormField
from apps.common.widgets.decimal import ArbitraryDecimalDisplayNumberInput

SITUACAO_CHOICES = (
    ("1", _("Paid")),
    ("0", _("Projected")),
)


def content_filter(queryset, name, value):
    queryset = queryset.filter(
        Q(description__icontains=value) | Q(notes__icontains=value)
    )
    return queryset


class MonthYearFilter(Filter):
    field_class = MonthYearFormField


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
        widget=TomSelectMultiple(checkboxes=True, remove_button=True, group_by="group"),
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
    date_start = django_filters.DateFilter(
        field_name="date",
        lookup_expr="gte",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        label=_("Date from"),
    )
    date_end = django_filters.DateFilter(
        field_name="date",
        lookup_expr="lte",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        label=_("Until"),
    )
    reference_date_start = MonthYearFilter(
        field_name="reference_date",
        lookup_expr="gte",
        label=_("Reference date from"),
    )
    reference_date_end = MonthYearFilter(
        field_name="reference_date",
        lookup_expr="lte",
        label=_("Until"),
    )
    from_amount = django_filters.NumberFilter(
        field_name="amount",
        lookup_expr="gte",
        label=_("Amount min"),
    )
    to_amount = django_filters.NumberFilter(
        field_name="amount",
        lookup_expr="lte",
        label=_("Amount max"),
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
            "date_start",
            "date_end",
            "reference_date_start",
            "reference_date_end",
            "from_amount",
            "to_amount",
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
            Row(Column("date_start"), Column("date_end")),
            Row(
                Column("reference_date_start", css_class="form-group col-md-6 mb-0"),
                Column("reference_date_end", css_class="form-group col-md-6 mb-0"),
                css_class="form-row",
            ),
            Row(
                Column("from_amount", css_class="form-group col-md-6 mb-0"),
                Column("to_amount", css_class="form-group col-md-6 mb-0"),
                css_class="form-row",
            ),
            Field("account", size=1),
            Field("category", size=1),
            Field("tags", size=1),
        )

        self.form.fields["to_amount"].widget = ArbitraryDecimalDisplayNumberInput()
        self.form.fields["from_amount"].widget = ArbitraryDecimalDisplayNumberInput()
