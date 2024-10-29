import datetime

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.calendar_view.utils.calendar import get_transactions_by_day
from apps.transactions.models import Transaction


@login_required
def index(request):
    now = timezone.localdate(timezone.now())

    return redirect(to="calendar", month=now.month, year=now.year)


@login_required
@require_http_methods(["GET"])
def calendar(request, month: int, year: int):
    if month < 1 or month > 12:
        from django.http import Http404

        raise Http404("Month is out of range")

    next_month = 1 if month == 12 else month + 1
    next_year = year + 1 if next_month == 1 and month == 12 else year

    previous_month = 12 if month == 1 else month - 1
    previous_year = year - 1 if previous_month == 12 and month == 1 else year

    return render(
        request,
        "calendar_view/pages/calendar.html",
        context={
            "month": month,
            "year": year,
            "next_month": next_month,
            "next_year": next_year,
            "previous_month": previous_month,
            "previous_year": previous_year,
        },
    )


@login_required
@require_http_methods(["GET"])
def calendar_list(request, month: int, year: int):
    today = timezone.localdate(timezone.now())
    dates = get_transactions_by_day(month=month, year=year)

    return render(
        request,
        "calendar_view/fragments/list.html",
        context={
            "month": month,
            "year": year,
            "today": today,
            "dates": dates,
        },
    )


@login_required
@require_http_methods(["GET"])
def calendar_transactions_list(request, day: int, month: int, year: int):
    date = datetime.date(year=year, month=month, day=day)
    transactions = Transaction.objects.filter(date=date).order_by(
        "date",
        "-type",
        "-is_paid",
        "id",
    )

    return render(
        request,
        "calendar_view/fragments/list_transactions.html",
        context={
            "date": date,
            "transactions": transactions,
        },
    )
