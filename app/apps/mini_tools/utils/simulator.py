from decimal import Decimal

from django.db.models import Case, DecimalField, F, Sum, Value, When
from django.db.models.functions import TruncMonth
from django.utils import timezone

from apps.accounts.models import Account
from apps.currencies.models import Currency
from apps.currencies.utils.convert import convert
from apps.transactions.models import Transaction


def get_simulator_baseline(user):
    """
    Build the projected baseline the simulator applies hypothetical entries on.

    For each currency, returns the projected net change (every transaction,
    paid or not) of each month that has transactions, keyed by "YYYY-MM", so
    the balance at the start of any month can be derived by summing every
    month before it. Archived and untracked accounts are ignored.

    Currencies with an exchange currency also carry the rate used to show
    their converted amounts.
    """
    accounts = Account.objects.filter(is_archived=False).exclude(
        id__in=user.untracked_accounts.values_list("id", flat=True)
    )
    currencies = (
        Currency.objects.filter(
            id__in=accounts.values_list("currency", flat=True), is_archived=False
        )
        .select_related("exchange_currency")
        .order_by("name")
    )

    monthly = {}
    for row in (
        Transaction.objects.filter(account__in=accounts)
        .annotate(month=TruncMonth("reference_date"))
        .values("account__currency", "month")
        .annotate(
            total=Sum(
                Case(
                    When(type=Transaction.Type.INCOME, then=F("amount")),
                    When(type=Transaction.Type.EXPENSE, then=-F("amount")),
                    default=Value(0),
                    output_field=DecimalField(),
                )
            )
        )
        .order_by()
    ):
        monthly.setdefault(row["account__currency"], {})[
            row["month"].strftime("%Y-%m")
        ] = float(row["total"] or 0)

    return {
        "current_month": timezone.localdate(timezone.now()).strftime("%Y-%m"),
        "currencies": [
            {
                "id": currency.id,
                "name": currency.name,
                "code": currency.code,
                "prefix": currency.prefix,
                "suffix": currency.suffix,
                "decimal_places": currency.decimal_places,
                "monthly": monthly.get(currency.id, {}),
                "exchange": _get_exchange(currency),
            }
            for currency in currencies
        ],
    }


def _get_exchange(currency):
    if not currency.exchange_currency:
        return None

    rate, prefix, suffix, decimal_places = convert(
        Decimal("1"), currency, currency.exchange_currency
    )
    if rate is None:
        return None

    return {
        "rate": float(rate),
        "prefix": prefix,
        "suffix": suffix,
        "decimal_places": decimal_places,
    }
