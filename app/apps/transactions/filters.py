import django_filters
from apps.accounts.models import Account
from apps.common.fields.month_year import MonthYearFormField
from apps.common.widgets.datepicker import AirDatePickerInput
from apps.common.widgets.decimal import ArbitraryDecimalDisplayNumberInput
from apps.common.widgets.tom_select import TomSelectMultiple
from apps.currencies.models import Currency
from apps.transactions.models import (
    SubTransaction,
    Transaction,
    TransactionCategory,
    TransactionEntity,
    TransactionTag,
)
from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Column, Div, Field, Layout, Row
from django import forms
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django_filters import Filter

SITUACAO_CHOICES = (
    ("1", _("Paid")),
    ("0", _("Projected")),
)

MUTE_STATUS_CHOICES = (
    ("active", _("Active")),
    ("muted", _("Muted")),
)


def content_filter(queryset, name, value):
    queryset = queryset.filter(
        Q(description__icontains=value)
        | Q(notes__icontains=value)
        # a subquery, so a transaction with several matching parts isn't listed twice
        | Q(pk__in=SubTransaction.objects.filter(name__icontains=value).values("transaction"))
    )
    return queryset


def exclude_matching(positive_filter):
    """Turn a positive filter method into one that drops the rows it would keep."""

    def method(queryset, name, value):
        if not value:
            return queryset
        matching = positive_filter(queryset, name, value)
        return queryset.exclude(pk__in=matching.values("pk"))

    return method


class MonthYearFilter(Filter):
    field_class = MonthYearFormField


class TransactionsFilter(django_filters.FilterSet):
    default_filter_values = {
        "type": {"IN", "EX"},
        "is_paid": {"1", "0"},
        "mute_status": {"active", "muted"},
    }

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
    mute_status = django_filters.MultipleChoiceFilter(
        choices=MUTE_STATUS_CHOICES,
        method="filter_mute_status",
        label=_("Mute Status"),
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
    exclude_description = django_filters.CharFilter(
        label=_("Content"),
        method=exclude_matching(content_filter),
        widget=forms.TextInput(attrs={"type": "search"}),
    )
    exclude_account = django_filters.ModelMultipleChoiceFilter(
        field_name="account__name",
        queryset=Account.objects.all(),
        to_field_name="name",
        exclude=True,
        label=_("Accounts"),
        widget=TomSelectMultiple(checkboxes=True, remove_button=True, group_by="group"),
    )
    exclude_currency = django_filters.ModelMultipleChoiceFilter(
        field_name="account__currency",
        queryset=Currency.objects.all(),
        to_field_name="id",
        exclude=True,
        label=_("Currencies"),
        widget=TomSelectMultiple(checkboxes=True, remove_button=True),
    )
    exclude_category = django_filters.MultipleChoiceFilter(
        label=_("Categories"),
        widget=TomSelectMultiple(checkboxes=True, remove_button=True),
        method="filter_exclude_category",
    )
    exclude_tags = django_filters.MultipleChoiceFilter(
        label=_("Tags"),
        widget=TomSelectMultiple(checkboxes=True, remove_button=True),
        method="filter_exclude_tags",
    )
    exclude_entities = django_filters.MultipleChoiceFilter(
        label=_("Entities"),
        widget=TomSelectMultiple(checkboxes=True, remove_button=True),
        method="filter_exclude_entities",
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

            if data.get("mute_status") is None:
                data.setlist("mute_status", ["active", "muted"])

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
            Field(
                "mute_status",
                template="transactions/widgets/transaction_type_filter_buttons.html",
            ),
            Div(
                HTML(
                    '<div role="tablist" class="tabs tabs-border mb-2">'
                    '<button type="button" role="tab" class="tab" '
                    ":class=\"{'tab-active': tab === 'include'}\" "
                    ":aria-selected=\"tab === 'include'\" "
                    "@click=\"tab = 'include'\">"
                    f"{_('Include')}</button>"
                    '<button type="button" role="tab" class="tab" '
                    ":class=\"{'tab-active': tab === 'exclude'}\" "
                    ":aria-selected=\"tab === 'exclude'\" "
                    "@click=\"tab = 'exclude'\">"
                    f"{_('Exclude')}</button>"
                    "</div>"
                ),
                Div(
                    Field("description"),
                    Row(Column("date_start"), Column("date_end")),
                    Row(
                        Column("reference_date_start"),
                        Column("reference_date_end"),
                    ),
                    Row(
                        Column("from_amount"),
                        Column("to_amount"),
                    ),
                    Field("account", size=1),
                    Field("currency", size=1),
                    Field("category", size=1),
                    Field("tags", size=1),
                    Field("entities", size=1),
                    role="tabpanel",
                    x_show="tab === 'include'",
                ),
                Div(
                    Field("exclude_description"),
                    Field("exclude_account", size=1),
                    Field("exclude_currency", size=1),
                    Field("exclude_category", size=1),
                    Field("exclude_tags", size=1),
                    Field("exclude_entities", size=1),
                    role="tabpanel",
                    x_show="tab === 'exclude'",
                    x_cloak="",
                ),
                x_data="{ tab: 'include' }",
            ),
        )

        self.form.fields["to_amount"].widget = ArbitraryDecimalDisplayNumberInput()
        self.form.fields["from_amount"].widget = ArbitraryDecimalDisplayNumberInput()
        self.form.fields["date_start"].widget = AirDatePickerInput()
        self.form.fields["date_end"].widget = AirDatePickerInput()

        self.form.fields["account"].queryset = Account.objects.all()
        self.form.fields["exclude_account"].queryset = Account.objects.all()
        category_choices = list(
            TransactionCategory.objects.values_list("name", "name").order_by("name")
        )
        custom_choices = [
            ("any", _("Categorized")),
            ("uncategorized", _("Uncategorized")),
        ]
        self.form.fields["category"].choices = custom_choices + category_choices
        self.form.fields["exclude_category"].choices = (
            custom_choices + category_choices
        )
        tag_choices = list(
            TransactionTag.objects.values_list("name", "name").order_by("name")
        )
        custom_tag_choices = [("any", _("Tagged")), ("untagged", _("Untagged"))]
        self.form.fields["tags"].choices = custom_tag_choices + tag_choices
        self.form.fields["exclude_tags"].choices = custom_tag_choices + tag_choices
        entity_choices = list(
            TransactionEntity.objects.values_list("name", "name").order_by("name")
        )
        custom_entity_choices = [
            ("any", _("Any entity")),
            ("no_entity", _("No entity")),
        ]
        self.form.fields["entities"].choices = custom_entity_choices + entity_choices
        self.form.fields["exclude_entities"].choices = (
            custom_entity_choices + entity_choices
        )

    @property
    def has_active_filters(self):
        for name in self.base_filters:
            if hasattr(self.form.data, "getlist"):
                values = self.form.data.getlist(name)
            else:
                value = self.form.data.get(name)
                values = value if isinstance(value, (list, tuple)) else [value]

            values = [str(value) for value in values if value not in (None, "")]
            if not values:
                continue
            if set(values) == self.default_filter_values.get(name):
                continue
            return True
        return False

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

    def filter_exclude_category(self, queryset, name, value):
        return exclude_matching(self.filter_category)(queryset, name, value)

    def filter_exclude_tags(self, queryset, name, value):
        return exclude_matching(self.filter_tags)(queryset, name, value)

    def filter_exclude_entities(self, queryset, name, value):
        return exclude_matching(self.filter_entities)(queryset, name, value)

    @staticmethod
    def filter_mute_status(queryset, name, value):
        from apps.common.middleware.thread_local import get_current_user

        if not value:
            return queryset

        value = list(value)

        # If both are selected, return all
        if "active" in value and "muted" in value:
            return queryset

        user = get_current_user()

        # Only Active selected: exclude muted transactions
        if "active" in value:
            return (
                queryset.exclude(account__untracked_by=user)
                .filter(
                    mute=False,
                )
                .filter(Q(category__mute=False) | Q(category__isnull=True))
            )

        # Only Muted selected: include only muted transactions
        if "muted" in value:
            return queryset.filter(
                Q(account__untracked_by=user) | Q(category__mute=True) | Q(mute=True)
            )

        return queryset
