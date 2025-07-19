from django.db.models import Q
from django.utils import timezone

from dateutil.relativedelta import relativedelta

from apps.transactions.models import Transaction
from apps.insights.forms import (
    SingleMonthForm,
    SingleYearForm,
    MonthRangeForm,
    YearRangeForm,
    DateRangeForm,
)


def get_transactions(request, include_unpaid=True, include_silent=False):
    transactions = Transaction.objects.all()

    filter_type = request.GET.get("type", None)

    if filter_type is not None:
        if filter_type == "month":
            form = SingleMonthForm(request.GET)

            if form.is_valid():
                month = form.cleaned_data["month"].replace(day=1)
            else:
                month = timezone.localdate(timezone.now()).replace(day=1)

            transactions = transactions.filter(
                reference_date__month=month.month, reference_date__year=month.year
            )
        elif filter_type == "year":
            form = SingleYearForm(request.GET)
            if form.is_valid():
                year = form.cleaned_data["year"].replace(day=1, month=1)
            else:
                year = timezone.localdate(timezone.now()).replace(day=1, month=1)

            transactions = transactions.filter(reference_date__year=year.year)
        elif filter_type == "month-range":
            form = MonthRangeForm(request.GET)
            if form.is_valid():
                month_from = form.cleaned_data["month_from"].replace(day=1)
                month_to = form.cleaned_data["month_to"].replace(day=1)
            else:
                month_from = timezone.localdate(timezone.now()).replace(day=1)
                month_to = (
                    timezone.localdate(timezone.now()) + relativedelta(months=1)
                ).replace(day=1)

            transactions = transactions.filter(
                reference_date__gte=month_from,
                reference_date__lte=month_to,
            )
        elif filter_type == "year-range":
            form = YearRangeForm(request.GET)
            if form.is_valid():
                year_from = form.cleaned_data["year_from"].replace(day=1, month=1)
                year_to = form.cleaned_data["year_to"].replace(day=31, month=12)
            else:
                year_from = timezone.localdate(timezone.now()).replace(day=1, month=1)
                year_to = (
                    timezone.localdate(timezone.now()) + relativedelta(years=1)
                ).replace(day=31, month=12)

            transactions = transactions.filter(
                reference_date__gte=year_from,
                reference_date__lte=year_to,
            )
        elif filter_type == "date-range":
            form = DateRangeForm(request.GET)
            if form.is_valid():
                date_from = form.cleaned_data["date_from"]
                date_to = form.cleaned_data["date_to"]
            else:
                date_from = timezone.localdate(timezone.now())
                date_to = timezone.localdate(timezone.now()) + relativedelta(months=1)

            transactions = transactions.filter(
                date__gte=date_from,
                date__lte=date_to,
            )
    else:  # Default to current month
        month = timezone.localdate(timezone.now())
        transactions = transactions.filter(
            reference_date__month=month.month, reference_date__year=month.year
        )

    if not include_unpaid:
        transactions = transactions.filter(is_paid=True)

    if not include_silent:
        transactions = transactions.exclude(
            Q(Q(category__mute=True) & ~Q(category=None)) | Q(mute=True)
        )

    return transactions
