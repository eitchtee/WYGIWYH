from collections import OrderedDict, defaultdict
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.db.models import Sum, Min, Max, Case, When, F, Value, DecimalField
from django.db.models.functions import TruncMonth
from django.template.defaultfilters import date as date_filter
from django.utils import timezone

from apps.accounts.models import Account
from apps.currencies.models import Currency
from apps.transactions.models import Transaction


def calculate_historical_currency_net_worth(is_paid=True):
    transactions_params = {**{k: v for k, v in [("is_paid", True)] if is_paid}}

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
        Transaction.objects.filter(**transactions_params)
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


def calculate_historical_account_balance(is_paid=True):
    transactions_params = {**{k: v for k, v in [("is_paid", True)] if is_paid}}
    # Get all accounts
    accounts = Account.objects.filter(
        is_archived=False,
    )

    # Get the date range
    date_range = Transaction.objects.filter(**transactions_params).aggregate(
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
        Transaction.objects.filter(**transactions_params)
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
