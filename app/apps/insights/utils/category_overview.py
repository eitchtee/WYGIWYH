from decimal import Decimal

from django.db import models
from django.db.models import Sum, Case, When, Value, DecimalField
from django.db.models.functions import Coalesce

from apps.transactions.models import Transaction
from apps.currencies.models import Currency
from apps.currencies.utils.convert import convert


def get_categories_totals(transactions_queryset, ignore_empty=False):
    # Get metrics for each category and currency in a single query
    category_currency_metrics = (
        transactions_queryset.values(
            "category",
            "category__name",
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
        .order_by("category__name")
    )

    # Process the results to structure by category
    result = {}

    for metric in category_currency_metrics:
        # Skip empty categories if ignore_empty is True
        if ignore_empty and all(
            metric[field] == Decimal("0")
            for field in [
                "expense_current",
                "expense_projected",
                "income_current",
                "income_projected",
            ]
        ):
            continue

        # Calculate derived totals
        total_current = metric["income_current"] - metric["expense_current"]
        total_projected = metric["income_projected"] - metric["expense_projected"]
        total_income = metric["income_current"] + metric["income_projected"]
        total_expense = metric["expense_current"] + metric["expense_projected"]
        total_final = total_current + total_projected

        category_id = metric["category"]
        currency_id = metric["account__currency"]

        if category_id not in result:
            result[category_id] = {"name": metric["category__name"], "currencies": {}}

        # Add currency data
        currency_data = {
            "currency": {
                "code": metric["account__currency__code"],
                "name": metric["account__currency__name"],
                "decimal_places": metric["account__currency__decimal_places"],
                "prefix": metric["account__currency__prefix"],
                "suffix": metric["account__currency__suffix"],
            },
            "expense_current": metric["expense_current"],
            "expense_projected": metric["expense_projected"],
            "total_expense": total_expense,
            "income_current": metric["income_current"],
            "income_projected": metric["income_projected"],
            "total_income": total_income,
            "total_current": total_current,
            "total_projected": total_projected,
            "total_final": total_final,
        }

        # Add exchanged values if exchange_currency exists
        if metric["account__currency__exchange_currency"]:
            from_currency = Currency.objects.get(id=currency_id)
            exchange_currency = Currency.objects.get(
                id=metric["account__currency__exchange_currency"]
            )

            exchanged = {}
            for field in [
                "expense_current",
                "expense_projected",
                "income_current",
                "income_projected",
                "total_income",
                "total_expense",
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

        result[category_id]["currencies"][currency_id] = currency_data

    return result
