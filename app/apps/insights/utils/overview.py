from decimal import Decimal

from django.db import models
from django.db.models import Sum, Case, When, Value
from django.db.models.functions import Coalesce

from apps.currencies.models import Currency
from apps.currencies.utils.convert import convert
from apps.transactions.models import Transaction

# Grouping levels an overview can be built from. Any ordering of these keys is a
# valid hierarchy, which is what makes the categories, tags and entities
# overviews the same view with a different level order.
LEVELS = {
    "categories": {"field": "category", "name": "category__name"},
    "tags": {"field": "tags", "name": "tags__name"},
    "entities": {"field": "entities", "name": "entities__name"},
}

CURRENCY_FIELDS = (
    "account__currency",
    "account__currency__code",
    "account__currency__name",
    "account__currency__decimal_places",
    "account__currency__prefix",
    "account__currency__suffix",
    "account__currency__exchange_currency",
)

# Aggregated amounts, plus the totals derived from them. Every one of these is
# converted when the account's currency has an exchange currency.
AGGREGATED_FIELDS = (
    "expense_current",
    "expense_projected",
    "income_current",
    "income_projected",
)
TOTAL_FIELDS = (
    "total_income",
    "total_expense",
    "total_current",
    "total_projected",
    "total_final",
)

# Fields picked for display, per "showing" mode. Doing it here keeps the
# templates down to one branch per cell instead of one per mode.
SHOWN_FIELDS = {
    "current": ("income_current", "expense_current", "total_current"),
    "projected": ("income_projected", "expense_projected", "total_projected"),
    "final": ("total_income", "total_expense", "total_final"),
}

# Key used for rows where the grouping field is null (untagged transactions, for
# instance). None is already a meaningful key for the top level, so children use
# a sentinel string to keep the dictionaries JSON serializable.
NO_VALUE = "none"


def _child_key(value):
    return NO_VALUE if value is None else value


def _sum_of(transaction_type, is_paid):
    return Coalesce(
        Sum(
            Case(
                When(type=transaction_type, is_paid=is_paid, then="amount"),
                default=Value(0),
                output_field=models.DecimalField(),
            )
        ),
        Decimal("0"),
    )


def _aggregate(transactions_queryset, group_fields, name_field):
    """Sum income/expense per currency, grouped by the given fields."""
    return (
        transactions_queryset.values(*group_fields, name_field, *CURRENCY_FIELDS)
        .annotate(
            expense_current=_sum_of(Transaction.Type.EXPENSE, is_paid=True),
            expense_projected=_sum_of(Transaction.Type.EXPENSE, is_paid=False),
            income_current=_sum_of(Transaction.Type.INCOME, is_paid=True),
            income_projected=_sum_of(Transaction.Type.INCOME, is_paid=False),
        )
        .order_by(name_field)
    )


def _build_currency_data(metric, showing):
    """Turn one aggregated row into the currency payload the templates read."""
    total_current = metric["income_current"] - metric["expense_current"]
    total_projected = metric["income_projected"] - metric["expense_projected"]

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
        "total_expense": metric["expense_current"] + metric["expense_projected"],
        "income_current": metric["income_current"],
        "income_projected": metric["income_projected"],
        "total_income": metric["income_current"] + metric["income_projected"],
        "total_current": total_current,
        "total_projected": total_projected,
        "total_final": total_current + total_projected,
    }

    income, expense, total = SHOWN_FIELDS.get(showing, SHOWN_FIELDS["final"])
    currency_data["shown"] = {
        "income": currency_data[income],
        "expense": currency_data[expense],
        "total": currency_data[total],
    }

    if metric["account__currency__exchange_currency"]:
        from_currency = Currency.objects.get(id=metric["account__currency"])
        exchange_currency = Currency.objects.get(
            id=metric["account__currency__exchange_currency"]
        )

        exchanged = {}
        for field in AGGREGATED_FIELDS + TOTAL_FIELDS:
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

    return currency_data


def get_grouped_totals(
    transactions_queryset, levels, showing="final", ignore_empty=False, depth=1
):
    """
    Build a nested income/expense breakdown of ``transactions_queryset``.

    ``showing`` picks which set of amounts lands in each row's ``shown`` key:
    ``current`` (paid only), ``projected`` (unpaid only) or ``final`` (both).

    ``levels`` is an ordered sequence of keys from ``LEVELS`` describing the
    hierarchy (e.g. ``("categories", "tags", "entities")``); ``depth`` says how
    many of those levels to actually aggregate, so the caller only pays for the
    rows it is going to show.

    Returns a dict keyed by the first level's id::

        {
            id: {
                "name": str | None,
                "search_path": str,
                "currencies": {currency_id: {...}},
                "children": {id: {"name": ..., "currencies": ..., "children": ...}},
            }
        }

    A null grouping value keeps ``None`` as the key at the top level and uses
    ``NO_VALUE`` further down; ``name`` is ``None`` in both cases so templates
    can render the label that fits the level.
    """
    levels = [level for level in levels if level in LEVELS][: max(depth, 1)]
    if not levels:
        return {}

    fields = [LEVELS[level]["field"] for level in levels]
    names = [LEVELS[level]["name"] for level in levels]

    result = {}

    for metric in _aggregate(transactions_queryset, fields[:1], names[0]):
        if ignore_empty and all(
            metric[field] == Decimal("0") for field in AGGREGATED_FIELDS
        ):
            continue

        node = result.setdefault(
            metric[fields[0]],
            {
                "name": metric[names[0]],
                "search_path": f"{len(result)}/",
                "currencies": {},
                "children": {},
            },
        )
        node["currencies"][metric["account__currency"]] = _build_currency_data(
            metric, showing
        )

    # Each extra level is aggregated on its own and grafted onto the node its
    # parent ids point at, so a child of a skipped (empty) parent is dropped.
    for index in range(1, len(levels)):
        for metric in _aggregate(
            transactions_queryset, fields[: index + 1], names[index]
        ):
            node = result.get(metric[fields[0]])
            for parent_field in fields[1:index]:
                if node is None:
                    break
                node = node["children"].get(_child_key(metric[parent_field]))

            if node is None:
                continue

            child = node["children"].setdefault(
                _child_key(metric[fields[index]]),
                {
                    "name": metric[names[index]],
                    "search_path": f"{node['search_path']}{len(node['children'])}/",
                    "currencies": {},
                    "children": {},
                },
            )
            child["currencies"][metric["account__currency"]] = _build_currency_data(
                metric, showing
            )

    return result
