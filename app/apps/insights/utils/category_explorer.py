from django.db.models import Sum, Case, When, F, DecimalField, Value
from django.db.models.functions import Coalesce
from django.utils.translation import gettext_lazy as _


def get_category_sums_by_account(queryset, category):
    """
    Returns income/expense sums per account for a specific category.
    """
    sums = (
        queryset.filter(category=category)
        .values("account__name")
        .annotate(
            income=Coalesce(
                Sum(
                    Case(
                        When(type="IN", then="amount"),
                        default=Value(0),
                        output_field=DecimalField(max_digits=42, decimal_places=30),
                    )
                ),
                Value(0),
                output_field=DecimalField(max_digits=42, decimal_places=30),
            ),
            expense=Coalesce(
                Sum(
                    Case(
                        When(type="EX", then=-F("amount")),
                        default=Value(0),
                        output_field=DecimalField(max_digits=42, decimal_places=30),
                    )
                ),
                Value(0),
                output_field=DecimalField(max_digits=42, decimal_places=30),
            ),
        )
        .order_by("account__name")
    )

    return {
        "labels": [item["account__name"] for item in sums],
        "datasets": [
            {
                "label": _("Income"),
                "data": [float(item["income"]) for item in sums],
            },
            {
                "label": _("Expenses"),
                "data": [float(item["expense"]) for item in sums],
            },
        ],
    }


def get_category_sums_by_currency(queryset, category):
    """
    Returns income/expense sums per currency for a specific category.
    """
    sums = (
        queryset.filter(category=category)
        .values("account__currency__name")
        .annotate(
            income=Coalesce(
                Sum(
                    Case(
                        When(type="IN", then="amount"),
                        default=Value(0),
                        output_field=DecimalField(max_digits=42, decimal_places=30),
                    )
                ),
                Value(0),
                output_field=DecimalField(max_digits=42, decimal_places=30),
            ),
            expense=Coalesce(
                Sum(
                    Case(
                        When(type="EX", then=-F("amount")),
                        default=Value(0),
                        output_field=DecimalField(max_digits=42, decimal_places=30),
                    )
                ),
                Value(0),
                output_field=DecimalField(max_digits=42, decimal_places=30),
            ),
        )
        .order_by("account__currency__name")
    )

    return {
        "labels": [item["account__currency__name"] for item in sums],
        "datasets": [
            {
                "label": _("Income"),
                "data": [float(item["income"]) for item in sums],
            },
            {
                "label": _("Expenses"),
                "data": [float(item["expense"]) for item in sums],
            },
        ],
    }
