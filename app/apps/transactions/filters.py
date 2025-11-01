import django_filters
from apps.accounts.models import Account
from apps.common.fields.month_year import MonthYearFormField
from apps.common.widgets.datepicker import AirDatePickerInput
from apps.common.widgets.decimal import ArbitraryDecimalDisplayNumberInput
from apps.common.widgets.tom_select import TomSelectMultiple
from apps.currencies.models import Currency
from apps.transactions.models import (
    Transaction,
    TransactionCategory,
    TransactionEntity,
    TransactionTag,
)
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Column, Field, Layout, Row
from django import forms
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django_filters import Filter

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
    currency = django_filters.ModelMultipleChoiceFilter(
        field_name="account__currency",
        queryset=Currency.objects.all(),
        to_field_name="id",
        label=_("Currencies"),
        widget=TomSelectMultiple(checkboxes=True, remove_button=True),
    )
    category = django_filters.MultipleChoiceFilter(
        label=_("Categories"),
        widget=TomSelectMultiple(checkboxes=True, remove_button=True),
        method="filter_category",
    )
    tags = django_filters.MultipleChoiceFilter(
        label=_("Tags"),
        widget=TomSelectMultiple(checkboxes=True, remove_button=True),
        method="filter_tags",
    )
    entities = django_filters.MultipleChoiceFilter(
        label=_("Entities"),
        widget=TomSelectMultiple(checkboxes=True, remove_button=True),
        method="filter_entities",
    )
    is_paid = django_filters.MultipleChoiceFilter(
        choices=SITUACAO_CHOICES,
        field_name="is_paid",
    )
    date_start = django_filters.DateFilter(
        field_name="date",
        lookup_expr="gte",
        label=_("Date from"),
    )
    date_end = django_filters.DateFilter(
        field_name="date",
        lookup_expr="lte",
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
            "entities",
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
                Column("reference_date_start", css_class="md:col-span-6 mb-0"),
                Column("reference_date_end", css_class="md:col-span-6 mb-0"),
                css_class="form-row",
            ),
            Row(
                Column("from_amount", css_class="md:col-span-6 mb-0"),
                Column("to_amount", css_class="md:col-span-6 mb-0"),
                css_class="form-row",
            ),
            Field("account", size=1),
            Field("currency", size=1),
            Field("category", size=1),
            Field("tags", size=1),
            Field("entities", size=1),
        )

        self.form.fields["to_amount"].widget = ArbitraryDecimalDisplayNumberInput()
        self.form.fields["from_amount"].widget = ArbitraryDecimalDisplayNumberInput()
        self.form.fields["date_start"].widget = AirDatePickerInput()
        self.form.fields["date_end"].widget = AirDatePickerInput()

        self.form.fields["account"].queryset = Account.objects.all()
        category_choices = list(
            TransactionCategory.objects.values_list("name", "name").order_by("name")
        )
        custom_choices = [
            ("any", _("Categorized")),
            ("uncategorized", _("Uncategorized")),
        ]
        self.form.fields["category"].choices = custom_choices + category_choices
        tag_choices = list(
            TransactionTag.objects.values_list("name", "name").order_by("name")
        )
        custom_tag_choices = [("any", _("Tagged")), ("untagged", _("Untagged"))]
        self.form.fields["tags"].choices = custom_tag_choices + tag_choices
        entity_choices = list(
            TransactionEntity.objects.values_list("name", "name").order_by("name")
        )
        custom_entity_choices = [
            ("any", _("Any entity")),
            ("no_entity", _("No entity")),
        ]
        self.form.fields["entities"].choices = custom_entity_choices + entity_choices

    @staticmethod
    def filter_category(queryset, name, value):
        if not value:
            return queryset

        value = list(value)

        if "any" in value:
            return queryset.filter(category__isnull=False)

        q = Q()
        if "uncategorized" in value:
            q |= Q(category__isnull=True)
            value.remove("uncategorized")

        if value:
            q |= Q(category__name__in=value)

        if q.children:
            return queryset.filter(q)

        return queryset

    @staticmethod
    def filter_tags(queryset, name, value):
        if not value:
            return queryset

        value = list(value)

        if "any" in value:
            return queryset.filter(tags__isnull=False).distinct()

        q = Q()
        if "untagged" in value:
            q |= Q(tags__isnull=True)
            value.remove("untagged")

        if value:
            q |= Q(tags__name__in=value)

        if q.children:
            return queryset.filter(q).distinct()

        return queryset

    @staticmethod
    def filter_entities(queryset, name, value):
        if not value:
            return queryset

        value = list(value)

        if "any" in value:
            return queryset.filter(entities__isnull=False).distinct()

        q = Q()
        if "no_entity" in value:
            q |= Q(entities__isnull=True)
            value.remove("no_entity")

        if value:
            q |= Q(entities__name__in=value)

        if q.children:
            return queryset.filter(q).distinct()

        return queryset
