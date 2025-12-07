from decimal import Decimal

from django.db import models

from apps.accounts.models import Account
from apps.transactions.models import Transaction


def get_account_balance(account: Account, paid_only: bool = True) -> Decimal:
    """
    Calculate account balance (income - expense).

    Args:
        account: Account instance to calculate balance for.
        paid_only: If True, only count paid transactions (current balance).
                   If False, count all transactions (projected balance).

    Returns:
        Decimal: The calculated balance (income - expense).
    """
    filters = {"account": account}
    if paid_only:
        filters["is_paid"] = True

    income = Transaction.objects.filter(
        type=Transaction.Type.INCOME, **filters
    ).aggregate(total=models.Sum("amount"))["total"] or Decimal("0")

    expense = Transaction.objects.filter(
        type=Transaction.Type.EXPENSE, **filters
    ).aggregate(total=models.Sum("amount"))["total"] or Decimal("0")

    return income - expense
