import calendar
from datetime import date

from apps.transactions.models import Transaction


def get_transactions_by_day(year, month):
    # Configure calendar to start on Monday
    calendar.setfirstweekday(calendar.MONDAY)

    # Get the first and last day of the month
    first_day = date(year, month, 1)
    last_day = date(year, month, calendar.monthrange(year, month)[1])

    # Get all transactions for the month
    transactions = Transaction.objects.filter(
        date__year=year, date__month=month
    ).order_by(
        "date",
        "-type",
        "-is_paid",
        "id",
    )

    # Calculate padding days needed at start
    start_padding = first_day.weekday()  # Monday is 0, Sunday is 6

    # Calculate padding days needed at end
    end_padding = (7 - last_day.weekday() - 1) % 7

    # Create padding days as empty dicts
    start_padding_dates = [{}] * start_padding
    end_padding_dates = [{}] * end_padding

    # Create current month days
    current_month_dates = [
        {"day": day, "date": date(year, month, day), "transactions": []}
        for day in range(1, calendar.monthrange(year, month)[1] + 1)
    ]

    # Group transactions by day
    for transaction in transactions:
        day = transaction.date.day
        for day_data in current_month_dates:
            if day_data["day"] == day:
                day_data["transactions"].append(transaction)
                break

    # Combine all dates
    result = start_padding_dates + current_month_dates + end_padding_dates

    return result
