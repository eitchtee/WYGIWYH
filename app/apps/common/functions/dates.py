import datetime
import calendar


def remaining_days_in_month(year, month, current_date: datetime.date):
    # Get the number of days in the given month
    _, days_in_month = calendar.monthrange(year, month)

    # Check if the given month and year match the current month and year
    if current_date.year == year and current_date.month == month:
        # Calculate remaining days
        remaining_days = days_in_month - current_date.day + 1
    else:
        # If not the current month, return the total number of days in the month
        remaining_days = days_in_month

    return remaining_days
