import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.db.models import Sum, Q, F, Case, When, DecimalField
from django.db.models.functions import Coalesce
from decimal import Decimal

from apps.transactions.forms import TransactionForm, TransferForm
from apps.transactions.models import Transaction
from apps.common.functions.dates import remaining_days_in_month


@login_required
def index(request):
    now = timezone.localdate(timezone.now())

    return redirect(to="transactions_overview", month=now.month, year=now.year)


@login_required
def transactions_overview(request, month: int, year: int):
    from django.utils.formats import get_format
    from django.utils.translation import get_language

    current_language = get_language()

    thousand_separator = get_format("THOUSAND_SEPARATOR")
    print(thousand_separator, current_language)
    if month < 1 or month > 12:
        from django.http import Http404

        raise Http404("Month is out of range")

    next_month = 1 if month == 12 else month + 1
    next_year = year + 1 if next_month == 1 and month == 12 else year

    previous_month = 12 if month == 1 else month - 1
    previous_year = year - 1 if previous_month == 12 and month == 1 else year

    return render(
        request,
        "transactions/overview.html",
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
def transactions_list(request, month: int, year: int):
    from django.db.models.functions import ExtractMonth, ExtractYear

    queryset = (
        Transaction.objects.annotate(
            month=ExtractMonth("reference_date"), year=ExtractYear("reference_date")
        )
        .values("month", "year")
        .distinct()
        .order_by("year", "month")
    )
    # print(queryset)

    transactions = (
        Transaction.objects.all()
        .filter(
            reference_date__year=year,
            reference_date__month=month,
        )
        .order_by("date", "id")
        .select_related()
    )

    return render(
        request,
        "transactions/fragments/list.html",
        context={"transactions": transactions},
    )


@login_required
def transaction_add(request, **kwargs):
    month = int(request.GET.get("month", timezone.localdate(timezone.now()).month))
    year = int(request.GET.get("year", timezone.localdate(timezone.now()).year))
    transaction_type = Transaction.Type(request.GET.get("type", "IN"))

    now = timezone.localdate(timezone.now())
    expected_date = datetime.datetime(
        day=now.day if month == now.month and year == now.year else 1,
        month=month,
        year=year,
    ).date()

    if request.method == "POST":
        form = TransactionForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("Transaction added successfully!"))

            # redirect to a new URL:
            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "transaction_updated, hide_offcanvas, toast"},
            )
    else:
        form = TransactionForm(
            initial={
                "reference_date": expected_date,
                "date": expected_date,
                "type": transaction_type,
            }
        )

    return render(
        request,
        "transactions/fragments/add.html",
        {"form": form},
    )


@login_required
def transaction_edit(request, transaction_id, **kwargs):
    transaction = get_object_or_404(Transaction, id=transaction_id)

    if request.method == "POST":
        form = TransactionForm(request.POST, instance=transaction)
        if form.is_valid():
            form.save()
            messages.success(request, _("Transaction updated successfully!"))

            # redirect to a new URL:
            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "transaction_updated, hide_offcanvas, toast"},
            )
    else:
        form = TransactionForm(instance=transaction)

    return render(
        request,
        "transactions/fragments/edit.html",
        {"form": form, "transaction": transaction},
    )


@login_required
def transaction_delete(request, transaction_id, **kwargs):
    transaction = get_object_or_404(Transaction, id=transaction_id)

    transaction.delete()

    messages.success(request, _("Transaction deleted successfully!"))

    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "transaction_updated, toast"},
    )


@login_required
def transactions_transfer(request):
    month = int(request.GET.get("month", timezone.localdate(timezone.now()).month))
    year = int(request.GET.get("year", timezone.localdate(timezone.now()).year))

    now = timezone.localdate(timezone.now())
    expected_date = datetime.datetime(
        day=now.day if month == now.month and year == now.year else 1,
        month=month,
        year=year,
    ).date()

    if request.method == "POST":
        form = TransferForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("Transfer added successfully."))
            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "transaction_updated, toast, hide_offcanvas"},
            )
    else:
        form = TransferForm(
            initial={
                "reference_date": expected_date,
                "date": expected_date,
            }
        )

    return render(request, "transactions/fragments/transfer.html", {"form": form})


@login_required
def transaction_pay(request, transaction_id):
    transaction = get_object_or_404(Transaction, pk=transaction_id)
    new_is_paid = False if transaction.is_paid else True
    transaction.is_paid = new_is_paid
    transaction.save()

    response = render(
        request,
        "transactions/fragments/item.html",
        context={"transaction": transaction},
    )
    response.headers["HX-Trigger"] = (
        f'{"paid" if new_is_paid else "unpaid"}, transaction_updated'
    )
    return response


@login_required
def month_year_picker(request):
    current_month = int(
        request.GET.get("month", timezone.localdate(timezone.now()).month)
    )
    current_year = int(request.GET.get("year", timezone.localdate(timezone.now()).year))

    available_years = Transaction.objects.dates(
        "reference_date", "year", order="ASC"
    ) or [datetime.datetime(current_year, current_month, 1)]

    return render(
        request,
        "transactions/fragments/month_year_picker.html",
        {
            "available_years": available_years,
            "months": range(1, 13),
            "current_month": current_month,
            "current_year": current_year,
        },
    )


@login_required
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
                "amount": round(
                    item["total"], item["account__currency__decimal_places"]
                ),
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
                "amount": round(
                    amount,
                    next(
                        (
                            item["account__currency__decimal_places"]
                            for item in list(income) + list(expenses)
                            if item["account__currency__name"] == currency
                        ),
                        2,
                    ),
                ),
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
                "amount": round(
                    amount,
                    next(
                        item["decimal_places"]
                        for item in total1 + total2
                        if item["currency"] == currency
                    ),
                ),
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

    # Construct the response dictionary
    response_data = {
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
        "transactions/fragments/monthly_summary.html",
        context={
            "totals": response_data,
        },
    )
