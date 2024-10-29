from datetime import datetime, date
import calendar

from apps.transactions.models import Transaction


# def get_transactions_by_day(year, month):
#     # Get all transactions for the month
#     transactions = Transaction.objects.filter(
#         date__year=year, date__month=month
#     ).order_by("date")
#
#     # Create a dictionary with all days of the month
#     all_days = {
#         day: {"day": day, "date": date(year, month, day), "transactions": []}
#         for day in range(1, calendar.monthrange(year, month)[1] + 1)
#     }
#
#     # Group transactions by day
#     for transaction in transactions:
#         day = transaction.date.day
#         all_days[day]["transactions"].append(transaction)
#
#     # Convert to list and sort by day
#     result = list(all_days.values())
#
#     return result


def get_transactions_by_day(year, month):
    # Configure calendar to start on Monday
    calendar.setfirstweekday(calendar.MONDAY)

    # Get the first and last day of the month
    first_day = date(year, month, 1)

    # Get all transactions for the month
    transactions = Transaction.objects.filter(
        date__year=year, date__month=month
    ).order_by("date")

    # Calculate padding days needed
    padding_days = first_day.weekday()  # Monday is 0, Sunday is 6

    # Create padding days as empty dicts
    padding_dates = [{}] * padding_days

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

    # Combine padding and current month dates
    result = padding_dates + current_month_dates

    return result
