from django.db.models import Sum, Case, When, F, DecimalField, Value
from django.db.models.functions import Coalesce
from django.utils.translation import gettext_lazy as _


def get_category_sums_by_account(queryset, category=None):
    """
    Returns income/expense sums per account for a specific category.
    """
    sums = (
        queryset.filter(category=category)
        .values("account__name")
        .annotate(
            current_income=Coalesce(
                Sum(
                    Case(
                        When(type="IN", is_paid=True, then="amount"),
                        default=Value(0),
                        output_field=DecimalField(max_digits=42, decimal_places=30),
                    )
                ),
                Value(0),
                output_field=DecimalField(max_digits=42, decimal_places=30),
            ),
            current_expense=Coalesce(
                Sum(
                    Case(
                        When(type="EX", is_paid=True, then=-F("amount")),
                        default=Value(0),
                        output_field=DecimalField(max_digits=42, decimal_places=30),
                    )
                ),
                Value(0),
                output_field=DecimalField(max_digits=42, decimal_places=30),
            ),
            projected_income=Coalesce(
                Sum(
                    Case(
                        When(type="IN", is_paid=False, then="amount"),
                        default=Value(0),
                        output_field=DecimalField(max_digits=42, decimal_places=30),
                    )
                ),
                Value(0),
                output_field=DecimalField(max_digits=42, decimal_places=30),
            ),
            projected_expense=Coalesce(
                Sum(
                    Case(
                        When(type="EX", is_paid=False, then=-F("amount")),
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
                "label": _("Current Income"),
                "data": [float(item["current_income"]) for item in sums],
            },
            {
                "label": _("Current Expenses"),
                "data": [float(item["current_expense"]) for item in sums],
            },
            {
                "label": _("Projected Income"),
                "data": [float(item["projected_income"]) for item in sums],
            },
            {
                "label": _("Projected Expenses"),
                "data": [float(item["projected_expense"]) for item in sums],
            },
        ],
    }


def get_category_sums_by_currency(queryset, category=None):
    """
    Returns income/expense sums per currency for a specific category.
    """
    sums = (
        queryset.filter(category=category)
        .values("account__currency__name")
        .annotate(
            current_income=Coalesce(
                Sum(
                    Case(
                        When(type="IN", is_paid=True, then="amount"),
                        default=Value(0),
                        output_field=DecimalField(max_digits=42, decimal_places=30),
                    )
                ),
                Value(0),
                output_field=DecimalField(max_digits=42, decimal_places=30),
            ),
            current_expense=Coalesce(
                Sum(
                    Case(
                        When(type="EX", is_paid=True, then=-F("amount")),
                        default=Value(0),
                        output_field=DecimalField(max_digits=42, decimal_places=30),
                    )
                ),
                Value(0),
                output_field=DecimalField(max_digits=42, decimal_places=30),
            ),
            projected_income=Coalesce(
                Sum(
                    Case(
                        When(type="IN", is_paid=False, then="amount"),
                        default=Value(0),
                        output_field=DecimalField(max_digits=42, decimal_places=30),
                    )
                ),
                Value(0),
                output_field=DecimalField(max_digits=42, decimal_places=30),
            ),
            projected_expense=Coalesce(
                Sum(
                    Case(
                        When(type="EX", is_paid=False, then=-F("amount")),
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
                "label": _("Current Income"),
                "data": [float(item["current_income"]) for item in sums],
            },
            {
                "label": _("Current Expenses"),
                "data": [float(item["current_expense"]) for item in sums],
            },
            {
                "label": _("Projected Income"),
                "data": [float(item["projected_income"]) for item in sums],
            },
            {
                "label": _("Projected Expenses"),
                "data": [float(item["projected_expense"]) for item in sums],
            },
        ],
    }
