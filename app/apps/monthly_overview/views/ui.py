from dateutil.relativedelta import relativedelta
from django.db.models import (
    Count,
)
from django.db.models.functions import ExtractYear, ExtractMonth
from django.shortcuts import render
from django.utils import timezone

from apps.transactions.models import Transaction


def month_year_picker(request):
    # Get current month and year from request or use current date
    current_date = timezone.localdate(timezone.now())
    current_month = int(request.GET.get("month", current_date.month))
    current_year = int(request.GET.get("year", current_date.year))

    # Set start and end dates
    start_date = timezone.datetime(current_year - 1, 1, 1).date()
    end_date = timezone.datetime(current_year + 1, 12, 31).date()

    # Get years from transactions
    transaction_years = Transaction.objects.dates("reference_date", "year", order="ASC")

    # Extend start_date and end_date if necessary
    if transaction_years:
        start_date = min(start_date, transaction_years.first().replace(month=1, day=1))
        end_date = max(end_date, transaction_years.last().replace(month=12, day=31))

    # Generate all months between start_date and end_date
    all_months = []
    current_month_date = start_date
    while current_month_date <= end_date:
        all_months.append(current_month_date)
        current_month_date += relativedelta(months=1)

    # Get transaction counts for each month
    transaction_counts = (
        Transaction.objects.annotate(
            year=ExtractYear("reference_date"), month=ExtractMonth("reference_date")
        )
        .values("year", "month")
        .annotate(transaction_count=Count("id"))
        .order_by("year", "month")
    )

    # Create a dictionary for quick lookup
    count_dict = {
        (item["year"], item["month"]): item["transaction_count"]
        for item in transaction_counts
    }

    # Create the final result
    result = [
        {
            "year": date.year,
            "month": date.month,
            "transaction_count": count_dict.get((date.year, date.month), 0),
        }
        for date in all_months
    ]

    return render(
        request,
        "monthly_overview/fragments/month_year_picker.html",
        {
            "month_year_data": result,
            "current_month": current_month,
            "current_year": current_year,
        },
    )