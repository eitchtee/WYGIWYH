from decimal import Decimal

from django.db.models import Sum


def calculate_sum(queryset, transaction_type, is_paid):
    return (
        queryset.filter(type=transaction_type, is_paid=is_paid)
        .values(
            "account__currency__name",
            "account__currency__suffix",
            "account__currency__prefix",
            "account__currency__decimal_places",
        )
        .annotate(total=Sum("amount"))
        .order_by("account__currency__name")
    )


# Helper function to format currency sums
def format_currency_sum(queryset):
    return [
        {
            "currency": item["account__currency__name"],
            "suffix": item["account__currency__suffix"],
            "prefix": item["account__currency__prefix"],
            "decimal_places": item["account__currency__decimal_places"],
            "amount": item["total"],
        }
        for item in queryset
    ]


# Calculate totals
def calculate_total(income, expenses):
    totals = {}

    # Process income
    for item in income:
        currency = item["account__currency__name"]
        totals[currency] = totals.get(currency, Decimal("0")) + item["total"]

    # Subtract expenses
    for item in expenses:
        currency = item["account__currency__name"]
        totals[currency] = totals.get(currency, Decimal("0")) - item["total"]

    return [
        {
            "currency": currency,
            "suffix": next(
                (
                    item["account__currency__suffix"]
                    for item in list(income) + list(expenses)
                    if item["account__currency__name"] == currency
                ),
                "",
            ),
            "prefix": next(
                (
                    item["account__currency__prefix"]
                    for item in list(income) + list(expenses)
                    if item["account__currency__name"] == currency
                ),
                "",
            ),
            "decimal_places": next(
                (
                    item["account__currency__decimal_places"]
                    for item in list(income) + list(expenses)
                    if item["account__currency__name"] == currency
                ),
                2,
            ),
            "amount": amount,
        }
        for currency, amount in totals.items()
    ]


# Calculate total final
def sum_totals(total1, total2):
    totals = {}
    for item in total1 + total2:
        currency = item["currency"]
        totals[currency] = totals.get(currency, Decimal("0")) + item["amount"]
    return [
        {
            "currency": currency,
            "suffix": next(
                item["suffix"]
                for item in total1 + total2
                if item["currency"] == currency
            ),
            "prefix": next(
                item["prefix"]
                for item in total1 + total2
                if item["currency"] == currency
            ),
            "decimal_places": next(
                item["decimal_places"]
                for item in total1 + total2
                if item["currency"] == currency
            ),
            "amount": amount,
        }
        for currency, amount in totals.items()
    ]
