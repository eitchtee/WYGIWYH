from decimal import Decimal
from django.utils import timezone
from calendar import monthrange

from apps.common.functions.dates import remaining_days_in_month


def calculate_daily_allowance_currency(currency_totals, month=None, year=None):
    """
    Calculate daily spending allowance based on currency totals.

    Args:
        currency_totals (dict): Result from calculate_currency_totals function
        month (int, optional): Month to calculate for. Defaults to current month.
        year (int, optional): Year to calculate for. Defaults to current year.

    Returns:
        dict: Daily allowance per currency, or empty dict if not current month
    """
    print(currency_totals)
    # If month/year not provided, use current date
    current_date = timezone.localdate(timezone.now())
    if month is None:
        month = current_date.month
    if year is None:
        year = current_date.year

    # Only calculate if we're looking at the current month
    if current_date.month != month or current_date.year != year:
        return {}

    # Calculate remaining days in month
    _, days_in_month = monthrange(year, month)
    remaining_days = remaining_days_in_month(
        current_date=current_date, month=month, year=year
    )

    # Calculate daily allowance for each currency
    result = {}

    for currency_id, data in currency_totals.items():
        # Get the total_final value, skip if not present
        total_final = data.get("total_final")
        if total_final is None:
            continue

        # Calculate daily allowance
        daily_amount = (
            total_final / remaining_days if remaining_days > 0 else Decimal("0")
        )

        # Only include positive amounts
        if daily_amount > 0:
            result[currency_id] = {"currency": data["currency"], "amount": daily_amount}

            # Include exchanged amount if available
            if "exchanged" in data and "total_final" in data["exchanged"]:
                exchanged_daily = data["exchanged"]["total_final"] / remaining_days
                if exchanged_daily > 0:
                    result[currency_id]["exchanged"] = {
                        "currency": data["exchanged"]["currency"],
                        "amount": exchanged_daily,
                    }

    return result
