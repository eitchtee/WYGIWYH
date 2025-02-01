from decimal import Decimal

from django.db import models
from django.db.models import Q, Sum, Case, When, Value, F
from django.db.models.functions import Coalesce

from apps.transactions.models import Transaction
from apps.currencies.utils.convert import convert
from apps.currencies.models import Currency


def calculate_currency_totals(transactions_queryset, ignore_empty=False):
    # Prepare the aggregation expressions
    currency_totals = (
        transactions_queryset.values(
            "account__currency",
            "account__currency__code",
            "account__currency__name",
            "account__currency__decimal_places",
            "account__currency__prefix",
            "account__currency__suffix",
            "account__currency__exchange_currency",
        )
        .annotate(
            expense_current=Coalesce(
                Sum(
                    Case(
                        When(
                            type=Transaction.Type.EXPENSE, is_paid=True, then="amount"
                        ),
                        default=Value(0),
                        output_field=models.DecimalField(),
                    )
                ),
                Decimal("0"),
            ),
            expense_projected=Coalesce(
                Sum(
                    Case(
                        When(
                            type=Transaction.Type.EXPENSE, is_paid=False, then="amount"
                        ),
                        default=Value(0),
                        output_field=models.DecimalField(),
                    )
                ),
                Decimal("0"),
            ),
            income_current=Coalesce(
                Sum(
                    Case(
                        When(type=Transaction.Type.INCOME, is_paid=True, then="amount"),
                        default=Value(0),
                        output_field=models.DecimalField(),
                    )
                ),
                Decimal("0"),
            ),
            income_projected=Coalesce(
                Sum(
                    Case(
                        When(
                            type=Transaction.Type.INCOME, is_paid=False, then="amount"
                        ),
                        default=Value(0),
                        output_field=models.DecimalField(),
                    )
                ),
                Decimal("0"),
            ),
        )
        .order_by()
    )

    # First pass: Process basic totals and store all currency data
    result = {}
    currencies_using_exchange = (
        {}
    )  # Track which currencies use which exchange currencies

    for total in currency_totals:
        # Skip empty currencies if ignore_empty is True
        if ignore_empty and all(
            total[field] == Decimal("0")
            for field in [
                "expense_current",
                "expense_projected",
                "income_current",
                "income_projected",
            ]
        ):
            continue

        # Calculate derived totals
        total_current = total["income_current"] - total["expense_current"]
        total_projected = total["income_projected"] - total["expense_projected"]
        total_final = total_current + total_projected
        currency_id = total["account__currency"]
        from_currency = Currency.objects.get(id=currency_id)
        exchange_currency = (
            Currency.objects.get(id=total["account__currency__exchange_currency"])
            if total["account__currency__exchange_currency"]
            else None
        )

        currency_data = {
            "currency": {
                "code": total["account__currency__code"],
                "name": total["account__currency__name"],
                "decimal_places": total["account__currency__decimal_places"],
                "prefix": total["account__currency__prefix"],
                "suffix": total["account__currency__suffix"],
            },
            "expense_current": total["expense_current"],
            "expense_projected": total["expense_projected"],
            "income_current": total["income_current"],
            "income_projected": total["income_projected"],
            "total_current": total_current,
            "total_projected": total_projected,
            "total_final": total_final,
        }

        # Add exchanged values if exchange_currency exists
        if exchange_currency:
            exchanged = {}
            for field in [
                "expense_current",
                "expense_projected",
                "income_current",
                "income_projected",
                "total_current",
                "total_projected",
                "total_final",
            ]:
                amount, prefix, suffix, decimal_places = convert(
                    amount=currency_data[field],
                    from_currency=from_currency,
                    to_currency=exchange_currency,
                )
                if amount is not None:
                    exchanged[field] = amount
                    if "currency" not in exchanged:
                        exchanged["currency"] = {
                            "prefix": prefix,
                            "suffix": suffix,
                            "decimal_places": decimal_places,
                            "code": exchange_currency.code,
                            "name": exchange_currency.name,
                        }

            if exchanged:
                currency_data["exchanged"] = exchanged
                # Track which currencies are using which exchange currencies
                if exchange_currency.id not in currencies_using_exchange:
                    currencies_using_exchange[exchange_currency.id] = []
                currencies_using_exchange[exchange_currency.id].append(
                    {"currency_id": currency_id, "exchanged": exchanged}
                )

        result[currency_id] = currency_data

    # Second pass: Add consolidated totals for currencies that are used as exchange currencies
    for currency_id, currency_data in result.items():
        if currency_id in currencies_using_exchange:
            consolidated = {
                "currency": currency_data["currency"].copy(),
                "expense_current": currency_data["expense_current"],
                "expense_projected": currency_data["expense_projected"],
                "income_current": currency_data["income_current"],
                "income_projected": currency_data["income_projected"],
                "total_current": currency_data["total_current"],
                "total_projected": currency_data["total_projected"],
                "total_final": currency_data["total_final"],
            }

            # Add exchanged values from all currencies using this as exchange currency
            for using_currency in currencies_using_exchange[currency_id]:
                exchanged = using_currency["exchanged"]
                for field in [
                    "expense_current",
                    "expense_projected",
                    "income_current",
                    "income_projected",
                    "total_current",
                    "total_projected",
                    "total_final",
                ]:
                    if field in exchanged:
                        consolidated[field] += exchanged[field]

            result[currency_id]["consolidated"] = consolidated

    return result


def calculate_percentage_distribution(currency_totals):
    """
    Calculate percentage distribution of financial metrics for each currency.
    Returns a new dictionary with currency IDs as keys and percentage distributions.
    """
    percentages = {}

    for currency_id, data in currency_totals.items():
        # Calculate total volume of transactions
        total_volume = sum(
            [
                abs(data["income_current"]),
                abs(data["income_projected"]),
                abs(data["expense_current"]),
                abs(data["expense_projected"]),
            ]
        )

        # Initialize percentages for this currency
        percentages[currency_id] = {
            "currency": data["currency"],  # Keep currency info for reference
            "percentages": {},
        }

        # Calculate percentages if total_volume is not zero
        if total_volume > 0:
            percentages[currency_id]["percentages"] = {
                "income_current": (abs(data["income_current"]) / total_volume) * 100,
                "income_projected": (abs(data["income_projected"]) / total_volume)
                * 100,
                "expense_current": (abs(data["expense_current"]) / total_volume) * 100,
                "expense_projected": (abs(data["expense_projected"]) / total_volume)
                * 100,
            }
        else:
            percentages[currency_id]["percentages"] = {
                "income_current": 0,
                "income_projected": 0,
                "expense_current": 0,
                "expense_projected": 0,
            }

        # If there's exchanged data, calculate percentages for that too
        if "exchanged" in data:
            exchanged_total = sum(
                [
                    abs(data.get("exchanged", {}).get("income_current", Decimal("0"))),
                    abs(
                        data.get("exchanged", {}).get("income_projected", Decimal("0"))
                    ),
                    abs(data.get("exchanged", {}).get("expense_current", Decimal("0"))),
                    abs(data.get("exchanged", {}).get("income_current", Decimal("0"))),
                ]
            )

            percentages[currency_id]["exchanged"] = {
                "currency": data["exchanged"]["currency"],
                "percentages": {},
            }

            if exchanged_total > 0:
                percentages[currency_id]["exchanged"]["percentages"] = {
                    "income_current": (
                        abs(
                            data.get("exchanged", {}).get(
                                "income_current", Decimal("0")
                            )
                        )
                        / exchanged_total
                    )
                    * 100,
                    "income_projected": (
                        abs(
                            data.get("exchanged", {}).get(
                                "income_projected", Decimal("0")
                            )
                        )
                        / exchanged_total
                    )
                    * 100,
                    "expense_current": (
                        abs(
                            data.get("exchanged", {}).get(
                                "expense_current", Decimal("0")
                            )
                        )
                        / exchanged_total
                    )
                    * 100,
                    "expense_projected": (
                        abs(
                            data.get("exchanged", {}).get(
                                "income_current", Decimal("0")
                            )
                        )
                        / exchanged_total
                    )
                    * 100,
                }
            else:
                percentages[currency_id]["exchanged"]["percentages"] = {
                    "income_current": 0,
                    "income_projected": 0,
                    "expense_current": 0,
                    "expense_projected": 0,
                }

    return percentages


def calculate_account_totals(transactions_queryset, ignore_empty=False):
    # Prepare the aggregation expressions
    account_totals = transactions_queryset.values(
        "account",
        "account__name",
        "account__is_asset",
        "account__is_archived",
        "account__group__name",
        "account__group__id",
        "account__currency__id",
        "account__currency__code",
        "account__currency__name",
        "account__currency__decimal_places",
        "account__currency__prefix",
        "account__currency__suffix",
        "account__exchange_currency",
    ).annotate(
        expense_current=Coalesce(
            Sum(
                Case(
                    When(type=Transaction.Type.EXPENSE, is_paid=True, then="amount"),
                    default=Value(0),
                    output_field=models.DecimalField(),
                )
            ),
            Decimal("0"),
        ),
        expense_projected=Coalesce(
            Sum(
                Case(
                    When(type=Transaction.Type.EXPENSE, is_paid=False, then="amount"),
                    default=Value(0),
                    output_field=models.DecimalField(),
                )
            ),
            Decimal("0"),
        ),
        income_current=Coalesce(
            Sum(
                Case(
                    When(type=Transaction.Type.INCOME, is_paid=True, then="amount"),
                    default=Value(0),
                    output_field=models.DecimalField(),
                )
            ),
            Decimal("0"),
        ),
        income_projected=Coalesce(
            Sum(
                Case(
                    When(type=Transaction.Type.INCOME, is_paid=False, then="amount"),
                    default=Value(0),
                    output_field=models.DecimalField(),
                )
            ),
            Decimal("0"),
        ),
    )

    # Process the results and calculate additional totals
    result = {}
    for total in account_totals:
        # Skip empty accounts if ignore_empty is True
        if ignore_empty and all(
            total[field] == Decimal("0")
            for field in [
                "expense_current",
                "expense_projected",
                "income_current",
                "income_projected",
            ]
        ):
            continue

        # Calculate derived totals
        total_current = total["income_current"] - total["expense_current"]
        total_projected = total["income_projected"] - total["expense_projected"]
        total_final = total_current + total_projected

        account_id = total["account"]
        currency = Currency.objects.get(id=total["account__currency__id"])
        exchange_currency = (
            Currency.objects.get(id=total["account__exchange_currency"])
            if total["account__exchange_currency"]
            else None
        )

        account_data = {
            "account": {
                "name": total["account__name"],
                "is_asset": total["account__is_asset"],
                "is_archived": total["account__is_archived"],
                "group": total["account__group__name"],
                "group_id": total["account__group__id"],
            },
            "currency": {
                "code": total["account__currency__code"],
                "name": total["account__currency__name"],
                "decimal_places": total["account__currency__decimal_places"],
                "prefix": total["account__currency__prefix"],
                "suffix": total["account__currency__suffix"],
            },
            "expense_current": total["expense_current"],
            "expense_projected": total["expense_projected"],
            "income_current": total["income_current"],
            "income_projected": total["income_projected"],
            "total_current": total_current,
            "total_projected": total_projected,
            "total_final": total_final,
        }

        # Add exchanged values if exchange_currency exists
        if exchange_currency:
            exchanged = {}

            # Convert each value
            for field in [
                "expense_current",
                "expense_projected",
                "income_current",
                "income_projected",
                "total_current",
                "total_projected",
                "total_final",
            ]:
                amount, prefix, suffix, decimal_places = convert(
                    amount=account_data[field],
                    from_currency=currency,
                    to_currency=exchange_currency,
                )

                if amount is not None:
                    exchanged[field] = amount
                    if "currency" not in exchanged:
                        exchanged["currency"] = {
                            "prefix": prefix,
                            "suffix": suffix,
                            "decimal_places": decimal_places,
                            "code": exchange_currency.code,
                            "name": exchange_currency.name,
                        }

            # Only add exchanged data if at least one conversion was successful
            if exchanged:
                account_data["exchanged"] = exchanged

        result[account_id] = account_data

    return result
