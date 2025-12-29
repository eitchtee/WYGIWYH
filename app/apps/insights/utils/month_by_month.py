from collections import OrderedDict
from decimal import Decimal

from django.db import models
from django.db.models import Sum, Case, When, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.currencies.models import Currency
from apps.currencies.utils.convert import convert
from apps.transactions.models import Transaction


def get_month_by_month_data(year=None, group_by="categories"):
    """
    Aggregate transaction totals by month for a specific year, grouped by categories, tags, or entities.

    Args:
        year: The year to filter transactions (defaults to current year)
        group_by: One of "categories", "tags", or "entities"

    Returns:
        {
            "year": 2025,
            "available_years": [2025, 2024, ...],
            "months": [1, 2, 3, ..., 12],
            "items": {
                item_id: {
                    "name": "Item Name",
                    "month_totals": {
                        1: {"currencies": {...}},
                        ...
                    },
                    "total": {"currencies": {...}}
                },
                ...
            },
            "month_totals": {...},
            "grand_total": {"currencies": {...}}
        }
    """
    if year is None:
        year = timezone.localdate(timezone.now()).year

    # Base queryset - all paid transactions, non-muted
    transactions = Transaction.objects.filter(
        is_paid=True,
        account__is_archived=False,
    ).exclude(account__currency__is_archived=True)

    # Get available years for the selector
    available_years = list(
        transactions.values_list("reference_date__year", flat=True)
        .distinct()
        .order_by("-reference_date__year")
    )

    # Filter by the selected year
    transactions = transactions.filter(reference_date__year=year)

    # Define grouping fields based on group_by parameter
    if group_by == "tags":
        group_field = "tags"
        name_field = "tags__name"
    elif group_by == "entities":
        group_field = "entities"
        name_field = "entities__name"
    else:  # Default to categories
        group_field = "category"
        name_field = "category__name"

    # Months 1-12
    months = list(range(1, 13))

    if not available_years:
        return {
            "year": year,
            "available_years": [],
            "months": months,
            "items": {},
            "month_totals": {},
            "grand_total": {"currencies": {}},
        }

    # Aggregate by group, month, and currency
    metrics = (
        transactions.values(
            group_field,
            name_field,
            "reference_date__month",
            "account__currency",
            "account__currency__code",
            "account__currency__name",
            "account__currency__decimal_places",
            "account__currency__prefix",
            "account__currency__suffix",
            "account__currency__exchange_currency",
        )
        .annotate(
            expense_total=Coalesce(
                Sum(
                    Case(
                        When(type=Transaction.Type.EXPENSE, then="amount"),
                        default=Value(0),
                        output_field=models.DecimalField(),
                    )
                ),
                Decimal("0"),
            ),
            income_total=Coalesce(
                Sum(
                    Case(
                        When(type=Transaction.Type.INCOME, then="amount"),
                        default=Value(0),
                        output_field=models.DecimalField(),
                    )
                ),
                Decimal("0"),
            ),
        )
        .order_by(name_field, "reference_date__month")
    )

    # Build result structure
    result = {
        "year": year,
        "available_years": available_years,
        "months": months,
        "items": OrderedDict(),
        "month_totals": {},
        "grand_total": {"currencies": {}},
    }

    # Store currency info for later use in totals
    currency_info = {}

    for metric in metrics:
        item_id = metric[group_field]
        item_name = metric[name_field]
        month = metric["reference_date__month"]
        currency_id = metric["account__currency"]

        # Use a consistent key for None (uncategorized/untagged/no entity)
        item_key = item_id if item_id is not None else "__none__"

        if item_key not in result["items"]:
            result["items"][item_key] = {
                "name": item_name,
                "month_totals": {},
                "total": {"currencies": {}},
            }

        if month not in result["items"][item_key]["month_totals"]:
            result["items"][item_key]["month_totals"][month] = {"currencies": {}}

        # Calculate final total (income - expense)
        final_total = metric["income_total"] - metric["expense_total"]

        # Store currency info for totals calculation
        if currency_id not in currency_info:
            currency_info[currency_id] = {
                "code": metric["account__currency__code"],
                "name": metric["account__currency__name"],
                "decimal_places": metric["account__currency__decimal_places"],
                "prefix": metric["account__currency__prefix"],
                "suffix": metric["account__currency__suffix"],
                "exchange_currency_id": metric["account__currency__exchange_currency"],
            }

        currency_data = {
            "currency": {
                "code": metric["account__currency__code"],
                "name": metric["account__currency__name"],
                "decimal_places": metric["account__currency__decimal_places"],
                "prefix": metric["account__currency__prefix"],
                "suffix": metric["account__currency__suffix"],
            },
            "final_total": final_total,
            "income_total": metric["income_total"],
            "expense_total": metric["expense_total"],
        }

        # Handle currency conversion if exchange currency is set
        if metric["account__currency__exchange_currency"]:
            from_currency = Currency.objects.get(id=currency_id)
            exchange_currency = Currency.objects.get(
                id=metric["account__currency__exchange_currency"]
            )

            converted_amount, prefix, suffix, decimal_places = convert(
                amount=final_total,
                from_currency=from_currency,
                to_currency=exchange_currency,
            )

            if converted_amount is not None:
                currency_data["exchanged"] = {
                    "final_total": converted_amount,
                    "currency": {
                        "prefix": prefix,
                        "suffix": suffix,
                        "decimal_places": decimal_places,
                        "code": exchange_currency.code,
                        "name": exchange_currency.name,
                    },
                }

        result["items"][item_key]["month_totals"][month]["currencies"][currency_id] = (
            currency_data
        )

        # Accumulate item total (across all months for this item)
        if currency_id not in result["items"][item_key]["total"]["currencies"]:
            result["items"][item_key]["total"]["currencies"][currency_id] = {
                "currency": currency_data["currency"].copy(),
                "final_total": Decimal("0"),
            }
        result["items"][item_key]["total"]["currencies"][currency_id][
            "final_total"
        ] += final_total

        # Accumulate month total (across all items for this month)
        if month not in result["month_totals"]:
            result["month_totals"][month] = {"currencies": {}}
        if currency_id not in result["month_totals"][month]["currencies"]:
            result["month_totals"][month]["currencies"][currency_id] = {
                "currency": currency_data["currency"].copy(),
                "final_total": Decimal("0"),
            }
        result["month_totals"][month]["currencies"][currency_id]["final_total"] += (
            final_total
        )

        # Accumulate grand total
        if currency_id not in result["grand_total"]["currencies"]:
            result["grand_total"]["currencies"][currency_id] = {
                "currency": currency_data["currency"].copy(),
                "final_total": Decimal("0"),
            }
        result["grand_total"]["currencies"][currency_id]["final_total"] += final_total

    # Add currency conversion for item totals
    for item_key, item_data in result["items"].items():
        for currency_id, total_data in item_data["total"]["currencies"].items():
            if currency_info[currency_id]["exchange_currency_id"]:
                from_currency = Currency.objects.get(id=currency_id)
                exchange_currency = Currency.objects.get(
                    id=currency_info[currency_id]["exchange_currency_id"]
                )
                converted_amount, prefix, suffix, decimal_places = convert(
                    amount=total_data["final_total"],
                    from_currency=from_currency,
                    to_currency=exchange_currency,
                )
                if converted_amount is not None:
                    total_data["exchanged"] = {
                        "final_total": converted_amount,
                        "currency": {
                            "prefix": prefix,
                            "suffix": suffix,
                            "decimal_places": decimal_places,
                            "code": exchange_currency.code,
                            "name": exchange_currency.name,
                        },
                    }

    # Add currency conversion for month totals
    for month, month_data in result["month_totals"].items():
        for currency_id, total_data in month_data["currencies"].items():
            if currency_info[currency_id]["exchange_currency_id"]:
                from_currency = Currency.objects.get(id=currency_id)
                exchange_currency = Currency.objects.get(
                    id=currency_info[currency_id]["exchange_currency_id"]
                )
                converted_amount, prefix, suffix, decimal_places = convert(
                    amount=total_data["final_total"],
                    from_currency=from_currency,
                    to_currency=exchange_currency,
                )
                if converted_amount is not None:
                    total_data["exchanged"] = {
                        "final_total": converted_amount,
                        "currency": {
                            "prefix": prefix,
                            "suffix": suffix,
                            "decimal_places": decimal_places,
                            "code": exchange_currency.code,
                            "name": exchange_currency.name,
                        },
                    }

    # Add currency conversion for grand total
    for currency_id, total_data in result["grand_total"]["currencies"].items():
        if currency_info[currency_id]["exchange_currency_id"]:
            from_currency = Currency.objects.get(id=currency_id)
            exchange_currency = Currency.objects.get(
                id=currency_info[currency_id]["exchange_currency_id"]
            )
            converted_amount, prefix, suffix, decimal_places = convert(
                amount=total_data["final_total"],
                from_currency=from_currency,
                to_currency=exchange_currency,
            )
            if converted_amount is not None:
                total_data["exchanged"] = {
                    "final_total": converted_amount,
                    "currency": {
                        "prefix": prefix,
                        "suffix": suffix,
                        "decimal_places": decimal_places,
                        "code": exchange_currency.code,
                        "name": exchange_currency.name,
                    },
                }

    return result
