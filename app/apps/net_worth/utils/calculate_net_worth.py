from django.db.models import Sum
from decimal import Decimal

from django.db.models.functions import TruncMonth

from apps.transactions.models import Transaction
from apps.accounts.models import Account
from apps.currencies.models import Currency


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
        .annotate(month=TruncMonth("date"))
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
                date__lte=month,
            ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

            expenses = Transaction.objects.filter(
                account=account,
                type=Transaction.Type.EXPENSE,
                is_paid=True,
                date__lte=month,
            ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

            account_balance = income - expenses
            historical_net_worth[month_str][currency.code] += account_balance

    return historical_net_worth
