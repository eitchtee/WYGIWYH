from django.contrib.auth.decorators import login_required
from django.db.models import (
    Q,
)
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.common.decorators.htmx import only_htmx
from apps.common.utils.dicts import remove_falsey_entries
from apps.monthly_overview.utils.daily_spending_allowance import (
    calculate_daily_allowance_currency,
)
from apps.transactions.filters import TransactionsFilter
from apps.transactions.models import Transaction
from apps.transactions.utils.calculations import (
    calculate_currency_totals,
    calculate_percentage_distribution,
)
from apps.transactions.utils.default_ordering import default_order


@login_required
def index(request):
    now = timezone.localdate(timezone.now())

    return redirect(to="monthly_overview", month=now.month, year=now.year)


@login_required
@require_http_methods(["GET"])
def monthly_overview(request, month: int, year: int):
    order = request.session.get("monthly_transactions_order", "default")

    if month < 1 or month > 12:
        from django.http import Http404

        raise Http404("Month is out of range")

    next_month = 1 if month == 12 else month + 1
    next_year = year + 1 if next_month == 1 and month == 12 else year

    previous_month = 12 if month == 1 else month - 1
    previous_year = year - 1 if previous_month == 12 and month == 1 else year

    f = TransactionsFilter(request.GET)

    return render(
        request,
        "monthly_overview/pages/overview.html",
        context={
            "month": month,
            "year": year,
            "next_month": next_month,
            "next_year": next_year,
            "previous_month": previous_month,
            "previous_year": previous_year,
            "filter": f,
            "order": order,
        },
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def transactions_list(request, month: int, year: int):
    order = request.session.get("monthly_transactions_order", "default")

    if "order" in request.GET:
        order = request.GET["order"]
        if order != request.session.get("monthly_transactions_order", "default"):
            request.session["monthly_transactions_order"] = order

    f = TransactionsFilter(request.GET)
    transactions_filtered = (
        f.qs.filter()
        .filter(
            reference_date__year=year,
            reference_date__month=month,
        )
        .prefetch_related(
            "account",
            "account__group",
            "category",
            "tags",
            "account__exchange_currency",
            "account__currency",
            "installment_plan",
        )
    )

    transactions_filtered = default_order(transactions_filtered, order=order)

    return render(
        request,
        "monthly_overview/fragments/list.html",
        context={"transactions": transactions_filtered},
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def monthly_summary(request, month: int, year: int):
    # Base queryset with all required filters
    base_queryset = Transaction.objects.filter(
        reference_date__year=year, reference_date__month=month, account__is_asset=False
    ).exclude(Q(category__mute=True) & ~Q(category=None))

    data = calculate_currency_totals(base_queryset, ignore_empty=True)
    percentages = calculate_percentage_distribution(data)

    context = {
        "income_current": remove_falsey_entries(data, "income_current"),
        "income_projected": remove_falsey_entries(data, "income_projected"),
        "expense_current": remove_falsey_entries(data, "expense_current"),
        "expense_projected": remove_falsey_entries(data, "expense_projected"),
        "total_current": remove_falsey_entries(data, "total_current"),
        "total_final": remove_falsey_entries(data, "total_final"),
        "total_projected": remove_falsey_entries(data, "total_projected"),
        "daily_spending_allowance": calculate_daily_allowance_currency(
            currency_totals=data, month=month, year=year
        ),
        "percentages": percentages,
    }

    return render(
        request,
        "monthly_overview/fragments/monthly_summary.html",
        context=context,
    )
