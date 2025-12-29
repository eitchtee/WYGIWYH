from collections import OrderedDict
from decimal import Decimal

from django.db import models
from django.db.models import Sum, Case, When, Value
from django.db.models.functions import Coalesce

from apps.currencies.models import Currency
from apps.currencies.utils.convert import convert
from apps.transactions.models import Transaction


def get_year_by_year_data(group_by="categories"):
    """
    Aggregate transaction totals by year for categories, tags, or entities.

    Args:
        group_by: One of "categories", "tags", or "entities"

    Returns:
        {
            "years": [2025, 2024, ...],  # Sorted descending
            "items": {
                item_id: {
                    "name": "Item Name",
                    "year_totals": {
                        2025: {"currencies": {...}},
                        ...
                    },
                    "total": {"currencies": {...}}  # Sum across all years
                },
                ...
            },
            "year_totals": {  # Sum across all items for each year
                2025: {"currencies": {...}},
                ...
            },
            "grand_total": {"currencies": {...}}  # Sum of everything
        }
    """
    # Base queryset - all paid transactions, non-muted
    transactions = Transaction.objects.filter(
        is_paid=True,
        account__is_archived=False,
    ).exclude(account__currency__is_archived=True)

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

    # Get all unique years with transactions
    years = (
        transactions.values_list("reference_date__year", flat=True)
        .distinct()
        .order_by("-reference_date__year")
    )
    years = list(years)

    if not years:
        return {
            "years": [],
            "items": {},
            "year_totals": {},
            "grand_total": {"currencies": {}},
        }

    # Aggregate by group, year, and currency
    metrics = (
        transactions.values(
            group_field,
            name_field,
            "reference_date__year",
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
        .order_by(name_field, "-reference_date__year")
    )

    # Build result structure
    result = {
        "years": years,
        "items": OrderedDict(),
        "year_totals": {},  # Totals per year across all items
        "grand_total": {"currencies": {}},  # Grand total across everything
    }

    # Store currency info for later use in totals
    currency_info = {}

    for metric in metrics:
        item_id = metric[group_field]
        item_name = metric[name_field]
        year = metric["reference_date__year"]
        currency_id = metric["account__currency"]

        # Use a consistent key for None (uncategorized/untagged/no entity)
        item_key = item_id if item_id is not None else "__none__"

        if item_key not in result["items"]:
            result["items"][item_key] = {
                "name": item_name,
                "year_totals": {},
                "total": {"currencies": {}},  # Total for this item across all years
            }

        if year not in result["items"][item_key]["year_totals"]:
            result["items"][item_key]["year_totals"][year] = {"currencies": {}}

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

        result["items"][item_key]["year_totals"][year]["currencies"][currency_id] = (
            currency_data
        )

        # Accumulate item total (across all years for this item)
        if currency_id not in result["items"][item_key]["total"]["currencies"]:
            result["items"][item_key]["total"]["currencies"][currency_id] = {
                "currency": currency_data["currency"].copy(),
                "final_total": Decimal("0"),
            }
        result["items"][item_key]["total"]["currencies"][currency_id][
            "final_total"
        ] += final_total

        # Accumulate year total (across all items for this year)
        if year not in result["year_totals"]:
            result["year_totals"][year] = {"currencies": {}}
        if currency_id not in result["year_totals"][year]["currencies"]:
            result["year_totals"][year]["currencies"][currency_id] = {
                "currency": currency_data["currency"].copy(),
                "final_total": Decimal("0"),
            }
        result["year_totals"][year]["currencies"][currency_id]["final_total"] += (
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

    # Add currency conversion for year totals
    for year, year_data in result["year_totals"].items():
        for currency_id, total_data in year_data["currencies"].items():
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
