from collections import OrderedDict, defaultdict
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.db.models import (
    OuterRef,
    Subquery,
)
from django.db.models import Sum, Min, Max, Case, When, F, Value, DecimalField
from django.db.models.functions import Coalesce
from django.db.models.functions import TruncMonth
from django.template.defaultfilters import date as date_filter
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import Account
from apps.currencies.models import Currency
from apps.currencies.utils.convert import convert
from apps.transactions.models import Transaction


def calculate_account_net_worth():
    ungrouped_id = None  # Special ID for ungrouped accounts

    # Subquery to calculate balance for each account
    balance_subquery = (
        Transaction.objects.filter(account=OuterRef("pk"), is_paid=True)
        .values("account")
        .annotate(
            balance=Sum(
                Case(
                    When(type=Transaction.Type.INCOME, then=F("amount")),
                    When(type=Transaction.Type.EXPENSE, then=-F("amount")),
                    default=0,
                    output_field=DecimalField(),
                )
            )
        )
        .values("balance")
    )

    # Main query to fetch all account data
    accounts_data = Account.objects.annotate(
        balance=Coalesce(Subquery(balance_subquery), Decimal("0"))
    ).select_related("currency", "exchange_currency", "group")

    account_net_worth = {ungrouped_id: {"name": _("Ungrouped"), "accounts": {}}}

    for account in accounts_data:
        account_data = {
            "name": account.name,
            "balance": account.balance,
            "currency": {
                "code": account.currency.code,
                "name": account.currency.name,
                "prefix": account.currency.prefix,
                "suffix": account.currency.suffix,
                "decimal_places": account.currency.decimal_places,
            },
        }

        if account.exchange_currency:
            converted_amount, prefix, suffix, decimal_places = convert(
                amount=account.balance,
                from_currency=account.currency,
                to_currency=account.exchange_currency,
            )
            if converted_amount:
                account_data["exchange"] = {
                    "amount": converted_amount,
                    "prefix": prefix,
                    "suffix": suffix,
                    "decimal_places": decimal_places,
                }

        group_id = account.group.id if account.group else ungrouped_id
        group_name = account.group.name if account.group else _("Ungrouped")

        if group_id not in account_net_worth:
            account_net_worth[group_id] = {"name": group_name, "accounts": {}}

        account_net_worth[group_id]["accounts"][account.id] = account_data

    # Remove the "Ungrouped" category if it's empty
    if not account_net_worth[ungrouped_id]["accounts"]:
        del account_net_worth[ungrouped_id]

    return account_net_worth


def calculate_currency_net_worth():
    # Subquery to calculate balance for each currency
    balance_subquery = (
        Transaction.objects.filter(account__currency=OuterRef("pk"), is_paid=True)
        .values("account__currency")
        .annotate(
            balance=Sum(
                Case(
                    When(type=Transaction.Type.INCOME, then=F("amount")),
                    When(type=Transaction.Type.EXPENSE, then=-F("amount")),
                    default=0,
                    output_field=DecimalField(),
                )
            )
        )
        .values("balance")
    )

    # Main query to fetch all currency data
    currencies_data = Currency.objects.annotate(
        balance=Coalesce(Subquery(balance_subquery), Decimal("0"))
    )

    net_worth = {}
    for item in currencies_data:
        currency_name = item.name
        net_worth[currency_name] = {
            "amount": net_worth.get(currency_name, {}).get("amount", Decimal("0"))
            + item.balance,
            "code": item.code,
            "name": currency_name,
            "prefix": item.prefix,
            "suffix": item.suffix,
            "decimal_places": item.decimal_places,
        }

    return net_worth


def calculate_historical_currency_net_worth():
    # Get all currencies and date range in a single query
    aggregates = Transaction.objects.aggregate(
        min_date=Min("reference_date"),
        max_date=Max("reference_date"),
    )
    currencies = list(Currency.objects.values_list("name", flat=True))

    if not aggregates.get("min_date"):
        start_date = timezone.localdate(timezone.now())
    else:
        start_date = aggregates["min_date"].replace(day=1)

    if not aggregates.get("max_date"):
        end_date = timezone.localdate(timezone.now()) + relativedelta(months=1)
    else:
        end_date = aggregates["max_date"].replace(day=1)

    # Calculate cumulative balances for each account, currency, and month
    cumulative_balances = (
        Transaction.objects.filter(is_paid=True)
        .annotate(month=TruncMonth("reference_date"))
        .values("account__currency__name", "month")
        .annotate(
            balance=Sum(
                Case(
                    When(type=Transaction.Type.INCOME, then=F("amount")),
                    When(type=Transaction.Type.EXPENSE, then=-F("amount")),
                    default=Value(0),
                    output_field=DecimalField(),
                )
            )
        )
        .order_by("month", "account__currency__name")
    )

    # Create a dictionary to store cumulative balances
    balance_dict = {}
    for b in cumulative_balances:
        month = b["month"]
        currency = b["account__currency__name"]
        if month not in balance_dict:
            balance_dict[month] = {}
        balance_dict[month][currency] = b["balance"]

    # Initialize the result dictionary
    historical_net_worth = OrderedDict()

    # Calculate running totals for each month
    running_totals = {currency: Decimal("0.00") for currency in currencies}
    last_recorded_totals = running_totals.copy()

    current_month = start_date
    while current_month <= end_date:
        month_str = date_filter(current_month, "b Y")
        totals_changed = False

        for currency in currencies:
            balance_change = balance_dict.get(current_month, {}).get(
                currency, Decimal("0.00")
            )
            running_totals[currency] += balance_change
            if balance_change != Decimal("0.00"):
                totals_changed = True

        if totals_changed or not historical_net_worth:
            historical_net_worth[month_str] = running_totals.copy()
            last_recorded_totals = running_totals.copy()

        current_month += relativedelta(months=1)

    # Ensure the last month is always included
    if historical_net_worth and list(historical_net_worth.keys())[-1] != date_filter(
        end_date, "b Y"
    ):
        historical_net_worth[date_filter(end_date, "b Y")] = last_recorded_totals

    return historical_net_worth


def calculate_historical_account_balance():
    # Get all accounts
    accounts = Account.objects.all()

    # Get the date range
    date_range = Transaction.objects.filter(is_paid=True).aggregate(
        min_date=Min("reference_date"), max_date=Max("reference_date")
    )

    if not date_range.get("min_date"):
        start_date = timezone.localdate(timezone.now())
    else:
        start_date = date_range["min_date"].replace(day=1)

    if not date_range.get("max_date"):
        end_date = timezone.localdate(timezone.now()) + relativedelta(months=1)
    else:
        end_date = date_range["max_date"].replace(day=1)

    # Calculate balances for each account and month
    balances = (
        Transaction.objects.filter(is_paid=True)
        .annotate(month=TruncMonth("reference_date"))
        .values("account", "month")
        .annotate(
            balance=Sum(
                Case(
                    When(type=Transaction.Type.INCOME, then=F("amount")),
                    When(type=Transaction.Type.EXPENSE, then=-F("amount")),
                    default=0,
                    output_field=DecimalField(),
                )
            )
        )
        .order_by("account", "month")
    )

    # Organize data by account and month
    account_balances = defaultdict(lambda: defaultdict(Decimal))
    for balance in balances:
        account_balances[balance["account"]][balance["month"]] += balance["balance"]

    # Prepare the result
    historical_account_balance = OrderedDict()
    current_date = start_date
    previous_balances = {account.id: Decimal("0") for account in accounts}

    while current_date <= end_date:
        month_data = {}
        has_changes = False

        for account in accounts:
            running_balance = previous_balances[account.id] + account_balances[
                account.id
            ].get(current_date, Decimal("0"))

            if running_balance != previous_balances[account.id]:
                has_changes = True

            month_data[account.name] = running_balance
            previous_balances[account.id] = running_balance

        if has_changes or not historical_account_balance:
            historical_account_balance[date_filter(current_date, "b Y")] = month_data

        current_date += relativedelta(months=1)

    # Ensure the last month is always included
    if historical_account_balance and list(historical_account_balance.keys())[
        -1
    ] != date_filter(end_date, "b Y"):
        historical_account_balance[date_filter(end_date, "b Y")] = month_data

    return historical_account_balance
