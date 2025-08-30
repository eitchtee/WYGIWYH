from decimal import Decimal

from django.db import models
from django.db.models import Sum, Case, When, Value, DecimalField
from django.db.models.functions import Coalesce

from apps.transactions.models import Transaction
from apps.currencies.models import Currency
from apps.currencies.utils.convert import convert


def get_categories_totals(
    transactions_queryset, ignore_empty=False, show_entities=False
):
    # Step 1: Aggregate transaction data by category and currency.
    # This query calculates the total current and projected income/expense for each
    # category by grouping transactions and summing up their amounts based on their
    # type (income/expense) and payment status (paid/unpaid).
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

    # Step 2: Aggregate transaction data by tag, category, and currency.
    # This is similar to the category metrics but adds tags to the grouping,
    # allowing for a breakdown of totals by tag within each category. It also
    # handles untagged transactions, where the 'tags' field is None.
    tag_metrics = transactions_queryset.values(
        "category",
        "tags",
        "tags__name",
        "account__currency",
        "account__currency__code",
        "account__currency__name",
        "account__currency__decimal_places",
        "account__currency__prefix",
        "account__currency__suffix",
        "account__currency__exchange_currency",
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

    # Step 3: Initialize the main dictionary to structure the final results.
    # The data will be organized hierarchically: category -> currency -> tags -> entities.
    result = {}

    # Step 4: Process the aggregated category metrics to build the initial result structure.
    # This loop iterates through each category's metrics and populates the `result` dict.
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
            result[category_id] = {
                "name": metric["category__name"],
                "currencies": {},
                "tags": {},  # Add tags container
            }

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

        # Step 4a: Handle currency conversion for category totals if an exchange currency is defined.
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

    # Step 5: Process the aggregated tag metrics and integrate them into the result structure.
    for tag_metric in tag_metrics:
        category_id = tag_metric["category"]
        tag_id = tag_metric["tags"]  # Will be None for untagged transactions

        if category_id in result:
            # Initialize the tag container if not exists
            if "tags" not in result[category_id]:
                result[category_id]["tags"] = {}

            # Determine if this is a tagged or untagged transaction
            tag_key = tag_id if tag_id is not None else "untagged"
            tag_name = tag_metric["tags__name"] if tag_id is not None else None

            if tag_key not in result[category_id]["tags"]:
                result[category_id]["tags"][tag_key] = {
                    "name": tag_name,
                    "currencies": {},
                    "entities": {},
                }

            currency_id = tag_metric["account__currency"]

            # Calculate tag totals
            tag_total_current = (
                tag_metric["income_current"] - tag_metric["expense_current"]
            )
            tag_total_projected = (
                tag_metric["income_projected"] - tag_metric["expense_projected"]
            )
            tag_total_income = (
                tag_metric["income_current"] + tag_metric["income_projected"]
            )
            tag_total_expense = (
                tag_metric["expense_current"] + tag_metric["expense_projected"]
            )
            tag_total_final = tag_total_current + tag_total_projected

            tag_currency_data = {
                "currency": {
                    "code": tag_metric["account__currency__code"],
                    "name": tag_metric["account__currency__name"],
                    "decimal_places": tag_metric["account__currency__decimal_places"],
                    "prefix": tag_metric["account__currency__prefix"],
                    "suffix": tag_metric["account__currency__suffix"],
                },
                "expense_current": tag_metric["expense_current"],
                "expense_projected": tag_metric["expense_projected"],
                "total_expense": tag_total_expense,
                "income_current": tag_metric["income_current"],
                "income_projected": tag_metric["income_projected"],
                "total_income": tag_total_income,
                "total_current": tag_total_current,
                "total_projected": tag_total_projected,
                "total_final": tag_total_final,
            }

            # Step 5a: Handle currency conversion for tag totals.
            if tag_metric["account__currency__exchange_currency"]:
                from_currency = Currency.objects.get(id=currency_id)
                exchange_currency = Currency.objects.get(
                    id=tag_metric["account__currency__exchange_currency"]
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
                        amount=tag_currency_data[field],
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
                    tag_currency_data["exchanged"] = exchanged

            result[category_id]["tags"][tag_key]["currencies"][
                currency_id
            ] = tag_currency_data

    # Step 6: If requested, aggregate and process entity-level data.
    if show_entities:
        entity_metrics = transactions_queryset.values(
            "category",
            "tags",
            "entities",
            "entities__name",
            "account__currency",
            "account__currency__code",
            "account__currency__name",
            "account__currency__decimal_places",
            "account__currency__prefix",
            "account__currency__suffix",
            "account__currency__exchange_currency",
        ).annotate(
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

        for entity_metric in entity_metrics:
            category_id = entity_metric["category"]
            tag_id = entity_metric["tags"]
            entity_id = entity_metric["entities"]

            if category_id in result:
                tag_key = tag_id if tag_id is not None else "untagged"
                if tag_key in result[category_id]["tags"]:
                    entity_key = entity_id if entity_id is not None else "no_entity"
                    entity_name = (
                        entity_metric["entities__name"]
                        if entity_id is not None
                        else None
                    )

                    if "entities" not in result[category_id]["tags"][tag_key]:
                        result[category_id]["tags"][tag_key]["entities"] = {}

                    if (
                        entity_key
                        not in result[category_id]["tags"][tag_key]["entities"]
                    ):
                        result[category_id]["tags"][tag_key]["entities"][entity_key] = {
                            "name": entity_name,
                            "currencies": {},
                        }

                    currency_id = entity_metric["account__currency"]

                    entity_total_current = (
                        entity_metric["income_current"]
                        - entity_metric["expense_current"]
                    )
                    entity_total_projected = (
                        entity_metric["income_projected"]
                        - entity_metric["expense_projected"]
                    )
                    entity_total_income = (
                        entity_metric["income_current"]
                        + entity_metric["income_projected"]
                    )
                    entity_total_expense = (
                        entity_metric["expense_current"]
                        + entity_metric["expense_projected"]
                    )
                    entity_total_final = entity_total_current + entity_total_projected

                    entity_currency_data = {
                        "currency": {
                            "code": entity_metric["account__currency__code"],
                            "name": entity_metric["account__currency__name"],
                            "decimal_places": entity_metric[
                                "account__currency__decimal_places"
                            ],
                            "prefix": entity_metric["account__currency__prefix"],
                            "suffix": entity_metric["account__currency__suffix"],
                        },
                        "expense_current": entity_metric["expense_current"],
                        "expense_projected": entity_metric["expense_projected"],
                        "total_expense": entity_total_expense,
                        "income_current": entity_metric["income_current"],
                        "income_projected": entity_metric["income_projected"],
                        "total_income": entity_total_income,
                        "total_current": entity_total_current,
                        "total_projected": entity_total_projected,
                        "total_final": entity_total_final,
                    }

                    if entity_metric["account__currency__exchange_currency"]:
                        from_currency = Currency.objects.get(id=currency_id)
                        exchange_currency = Currency.objects.get(
                            id=entity_metric["account__currency__exchange_currency"]
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
                                amount=entity_currency_data[field],
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
                            entity_currency_data["exchanged"] = exchanged

                    result[category_id]["tags"][tag_key]["entities"][entity_key][
                        "currencies"
                    ][currency_id] = entity_currency_data

    return result
