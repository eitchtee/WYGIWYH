from django.db.models import Sum
from decimal import Decimal

from django.db.models.functions import TruncMonth
from django.utils.translation import gettext_lazy as _

from apps.transactions.models import Transaction
from apps.accounts.models import Account
from apps.currencies.models import Currency
from apps.currencies.utils.convert import convert


def calculate_account_net_worth():
    account_net_worth = {}
    ungrouped_id = None  # Special ID for ungrouped accounts

    # Initialize the "Ungrouped" category
    account_net_worth[ungrouped_id] = {"name": _("Ungrouped"), "accounts": {}}

    # Get all accounts
    accounts = Account.objects.all()

    for account in accounts:
        currency = account.currency

        income = Transaction.objects.filter(
            account=account, type=Transaction.Type.INCOME, is_paid=True
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

        expenses = Transaction.objects.filter(
            account=account, type=Transaction.Type.EXPENSE, is_paid=True
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

        account_balance = income - expenses

        account_data = {
            "name": account.name,
            "balance": account_balance,
            "currency": {
                "code": currency.code,
                "name": currency.name,
                "prefix": currency.prefix,
                "suffix": currency.suffix,
                "decimal_places": currency.decimal_places,
            },
        }

        if account.exchange_currency:
            converted_amount, prefix, suffix, decimal_places = convert(
                amount=account_balance,
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

        if account.group:
            group_id = account.group.id
            group_name = account.group.name
            if group_id not in account_net_worth:
                account_net_worth[group_id] = {"name": group_name, "accounts": {}}
            account_net_worth[group_id]["accounts"][account.id] = account_data
        else:
            account_net_worth[ungrouped_id]["accounts"][account.id] = account_data

    # Remove the "Ungrouped" category if it's empty
    if not account_net_worth[ungrouped_id]["accounts"]:
        del account_net_worth[ungrouped_id]

    return account_net_worth


def calculate_net_worth():
    accounts = Account.objects.all()
    net_worth = {}

    for account in accounts:
        currency = account.currency
        if currency.code not in net_worth:
            net_worth[currency.code] = Decimal("0")

        income = Transaction.objects.filter(
            account=account, type=Transaction.Type.INCOME, is_paid=True
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

        expenses = Transaction.objects.filter(
            account=account, type=Transaction.Type.EXPENSE, is_paid=True
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

        account_balance = income - expenses
        net_worth[currency.code] += account_balance

    return net_worth


def calculate_historical_net_worth(start_date, end_date):
    asset_accounts = Account.objects.all()
    currencies = Currency.objects.all()

    # Initialize the result dictionary
    historical_net_worth = {}

    # Get all months between start_date and end_date
    months = (
        Transaction.objects.filter(account__in=asset_accounts)
        .annotate(month=TruncMonth("reference_date"))
        .values("month")
        .distinct()
        .order_by("month")
    )

    for month_data in months:
        month = month_data["month"]
        month_str = month.strftime("%Y-%m")
        historical_net_worth[month_str] = {
            currency.code: Decimal("0.00") for currency in currencies
        }

        for account in asset_accounts:
            currency = account.currency

            income = Transaction.objects.filter(
                account=account,
                type=Transaction.Type.INCOME,
                is_paid=True,
                reference_date__lte=month,
            ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

            expenses = Transaction.objects.filter(
                account=account,
                type=Transaction.Type.EXPENSE,
                is_paid=True,
                reference_date__lte=month,
            ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

            account_balance = income - expenses
            historical_net_worth[month_str][currency.code] += account_balance

    return historical_net_worth
