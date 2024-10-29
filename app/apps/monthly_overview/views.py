from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import (
    Sum,
    Q,
)
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.common.decorators.htmx import only_htmx
from apps.common.functions.dates import remaining_days_in_month
from apps.transactions.filters import TransactionsFilter
from apps.transactions.models import Transaction
from apps.transactions.utils.default_ordering import default_order


@login_required
def index(request):
    now = timezone.localdate(timezone.now())

    return redirect(to="monthly_overview", month=now.month, year=now.year)


@login_required
@require_http_methods(["GET"])
def monthly_overview(request, month: int, year: int):
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
        },
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def transactions_list(request, month: int, year: int):
    order = request.GET.get("order")

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

    if order == "default":
        transactions_filtered = default_order(
            transactions_filtered, extra_ordering=["date", "id"]
        )
    elif order == "newer":
        transactions_filtered = transactions_filtered.order_by("-date", "id")
    elif order == "older":
        transactions_filtered = transactions_filtered.order_by("date", "id")
    else:
        transactions_filtered = transactions_filtered.order_by("date", "id")

    return render(
        request,
        "monthly_overview/fragments/list.html",
        context={"transactions": transactions_filtered},
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def monthly_summary(request, month: int, year: int):
    # Helper function to calculate sums for different transaction types
    def calculate_sum(transaction_type, is_paid):
        return (
            base_queryset.filter(type=transaction_type, is_paid=is_paid)
            .values(
                "account__currency__name",
                "account__currency__suffix",
                "account__currency__prefix",
                "account__currency__decimal_places",
            )
            .annotate(total=Sum("amount"))
            .order_by("account__currency__name")
        )

    # Helper function to format currency sums
    def format_currency_sum(queryset):
        return [
            {
                "currency": item["account__currency__name"],
                "suffix": item["account__currency__suffix"],
                "prefix": item["account__currency__prefix"],
                "decimal_places": item["account__currency__decimal_places"],
                "amount": item["total"],
            }
            for item in queryset
        ]

    # Calculate totals
    def calculate_total(income, expenses):
        totals = {}

        # Process income
        for item in income:
            currency = item["account__currency__name"]
            totals[currency] = totals.get(currency, Decimal("0")) + item["total"]

        # Subtract expenses
        for item in expenses:
            currency = item["account__currency__name"]
            totals[currency] = totals.get(currency, Decimal("0")) - item["total"]

        return [
            {
                "currency": currency,
                "suffix": next(
                    (
                        item["account__currency__suffix"]
                        for item in list(income) + list(expenses)
                        if item["account__currency__name"] == currency
                    ),
                    "",
                ),
                "prefix": next(
                    (
                        item["account__currency__prefix"]
                        for item in list(income) + list(expenses)
                        if item["account__currency__name"] == currency
                    ),
                    "",
                ),
                "decimal_places": next(
                    (
                        item["account__currency__decimal_places"]
                        for item in list(income) + list(expenses)
                        if item["account__currency__name"] == currency
                    ),
                    2,
                ),
                "amount": amount,
            }
            for currency, amount in totals.items()
        ]

    # Calculate total final
    def sum_totals(total1, total2):
        totals = {}
        for item in total1 + total2:
            currency = item["currency"]
            totals[currency] = totals.get(currency, Decimal("0")) + item["amount"]
        return [
            {
                "currency": currency,
                "suffix": next(
                    item["suffix"]
                    for item in total1 + total2
                    if item["currency"] == currency
                ),
                "prefix": next(
                    item["prefix"]
                    for item in total1 + total2
                    if item["currency"] == currency
                ),
                "decimal_places": next(
                    item["decimal_places"]
                    for item in total1 + total2
                    if item["currency"] == currency
                ),
                "amount": amount,
            }
            for currency, amount in totals.items()
        ]

    # Base queryset with all required filters
    base_queryset = Transaction.objects.filter(
        reference_date__year=year, reference_date__month=month, account__is_asset=False
    ).exclude(Q(category__mute=True) & ~Q(category=None))

    # Calculate sums for different transaction types
    paid_income = calculate_sum(Transaction.Type.INCOME, True)
    projected_income = calculate_sum(Transaction.Type.INCOME, False)
    paid_expenses = calculate_sum(Transaction.Type.EXPENSE, True)
    projected_expenses = calculate_sum(Transaction.Type.EXPENSE, False)

    total_current = calculate_total(paid_income, paid_expenses)
    total_projected = calculate_total(projected_income, projected_expenses)

    total_final = sum_totals(total_current, total_projected)

    # Calculate daily spending allowance
    remaining_days = remaining_days_in_month(
        month=month, year=year, current_date=timezone.localdate(timezone.now())
    )
    if (
        timezone.localdate(timezone.now()).month == month
        and timezone.localdate(timezone.now()).year == year
    ):
        daily_spending_allowance = [
            {
                "currency": item["currency"],
                "suffix": item["suffix"],
                "prefix": item["prefix"],
                "decimal_places": item["decimal_places"],
                "amount": (
                    amount
                    if (amount := item["amount"] / remaining_days) > 0
                    else Decimal("0")
                ),
            }
            for item in total_final
        ]
    else:
        daily_spending_allowance = []

    # Construct the response dictionary
    data = {
        "paid_income": format_currency_sum(paid_income),
        "projected_income": format_currency_sum(projected_income),
        "paid_expenses": format_currency_sum(paid_expenses),
        "projected_expenses": format_currency_sum(projected_expenses),
        "total_current": total_current,
        "total_projected": total_projected,
        "total_final": total_final,
        "daily_spending_allowance": daily_spending_allowance,
    }

    return render(
        request,
        "monthly_overview/fragments/monthly_summary.html",
        context={"totals": data},
    )