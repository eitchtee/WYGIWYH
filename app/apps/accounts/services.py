from datetime import date
from decimal import Decimal

from django.db import models

from apps.accounts.models import Account
from apps.transactions.models import Transaction


def get_account_balance(
    account: Account,
    paid_only: bool = True,
    date_lte: date | None = None,
    reference_date_lte: date | None = None,
) -> Decimal:
    """
    Calculate account balance (income - expense).

    Args:
        account: Account instance to calculate balance for.
        paid_only: If True, only count paid transactions (current balance).
                   If False, count all transactions (projected balance).
        date_lte: If set, only count transactions dated on or before it.
        reference_date_lte: If set, only count transactions whose reference
                            month is on or before it.

    Returns:
        Decimal: The calculated balance (income - expense).
    """
    filters = {"account": account}
    if paid_only:
        filters["is_paid"] = True
    if date_lte:
        filters["date__lte"] = date_lte
    if reference_date_lte:
        filters["reference_date__lte"] = reference_date_lte

    income = Transaction.objects.filter(
        type=Transaction.Type.INCOME, **filters
    ).aggregate(total=models.Sum("amount"))["total"] or Decimal("0")

    expense = Transaction.objects.filter(
        type=Transaction.Type.EXPENSE, **filters
    ).aggregate(total=models.Sum("amount"))["total"] or Decimal("0")

    return income - expense
