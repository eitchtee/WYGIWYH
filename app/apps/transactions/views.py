import datetime
from decimal import Decimal
from itertools import groupby
from operator import itemgetter

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, F, Case, When, DecimalField, Value, Q, CharField
from django.db.models.functions import Coalesce, ExtractMonth, ExtractYear
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from unicodedata import category

from apps.transactions.forms import TransactionForm
from apps.transactions.models import Transaction


@login_required
def index(request):
    now = timezone.now()

    return redirect(to="transactions_overview", month=now.month, year=now.year)


@login_required
def transactions_overview(request, month: int, year: int):
    if month < 1 or month > 12:
        from django.http import Http404

        raise Http404("Month is out of range")

    next_month = 1 if month == 12 else month + 1
    next_year = year + 1 if next_month == 1 and month == 12 else year

    previous_month = 12 if month == 1 else month - 1
    previous_year = year - 1 if previous_month == 12 and month == 1 else year

    print(
        Transaction.objects.annotate(
            month=ExtractMonth("reference_date"), year=ExtractYear("reference_date")
        )
        .values("month", "year")
        .distinct()
        .order_by("year", "month")
    )

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
def monthly_summary(request, month: int, year: int):
    queryset = (
        Transaction.objects.filter(
            Q(category__mute=False) | Q(category__isnull=True),
            account__is_asset=False,
            reference_date__year=year,
            reference_date__month=month,
        )
        .annotate(
            transaction_type=Value("expense", output_field=CharField()),
            is_paid_status=Value("paid", output_field=CharField()),
        )
        .filter(type=Transaction.Type.EXPENSE, is_paid=True)
        .values(
            "account__currency__name",
            "account__currency__prefix",
            "account__currency__suffix",
            "account__currency__decimal_places",
            "transaction_type",
            "is_paid_status",
        )
        .annotate(
            total_amount=Coalesce(
                Sum("amount"),
                0,
                output_field=DecimalField(max_digits=30, decimal_places=18),
            )
        )
        .union(
            Transaction.objects.filter(
                Q(category__mute=False) | Q(category__isnull=True),
                account__is_asset=False,
                reference_date__year=year,
                reference_date__month=month,
            )
            .annotate(
                transaction_type=Value("expense", output_field=CharField()),
                is_paid_status=Value("projected", output_field=CharField()),
            )
            .filter(type=Transaction.Type.EXPENSE, is_paid=False)
            .values(
                "account__currency__name",
                "account__currency__prefix",
                "account__currency__suffix",
                "account__currency__decimal_places",
                "transaction_type",
                "is_paid_status",
            )
            .annotate(
                total_amount=Coalesce(
                    Sum("amount"),
                    0,
                    output_field=DecimalField(max_digits=30, decimal_places=18),
                )
            )
        )
        .union(
            Transaction.objects.filter(
                Q(category__mute=False) | Q(category__isnull=True),
                account__is_asset=False,
                reference_date__year=year,
                reference_date__month=month,
            )
            .annotate(
                transaction_type=Value("income", output_field=CharField()),
                is_paid_status=Value("paid", output_field=CharField()),
            )
            .filter(type=Transaction.Type.INCOME, is_paid=True)
            .values(
                "account__currency__name",
                "account__currency__prefix",
                "account__currency__suffix",
                "account__currency__decimal_places",
                "transaction_type",
                "is_paid_status",
            )
            .annotate(
                total_amount=Coalesce(
                    Sum("amount"),
                    0,
                    output_field=DecimalField(max_digits=30, decimal_places=18),
                )
            )
        )
        .union(
            Transaction.objects.filter(
                Q(category__mute=False) | Q(category__isnull=True),
                account__is_asset=False,
                reference_date__year=year,
                reference_date__month=month,
            )
            .annotate(
                transaction_type=Value("income", output_field=CharField()),
                is_paid_status=Value("projected", output_field=CharField()),
            )
            .filter(type=Transaction.Type.INCOME, is_paid=False)
            .values(
                "account__currency__name",
                "account__currency__prefix",
                "account__currency__suffix",
                "account__currency__decimal_places",
                "transaction_type",
                "is_paid_status",
            )
            .annotate(
                total_amount=Coalesce(
                    Sum("amount"),
                    0,
                    output_field=DecimalField(max_digits=30, decimal_places=18),
                )
            )
        )
        .order_by("account__currency__name", "transaction_type", "is_paid_status")
    )

    result = {}
    for (transaction_type, is_paid_status), group in groupby(
        queryset, key=itemgetter("transaction_type", "is_paid_status")
    ):
        key = f"{is_paid_status}_{transaction_type}"
        result[key] = [
            {
                "name": item["account__currency__name"],
                "prefix": item["account__currency__prefix"],
                "suffix": item["account__currency__suffix"],
                "decimal_places": item["account__currency__decimal_places"],
                "total_amount": item["total_amount"],
            }
            for item in group
        ]

    # result["total_balance"] =
    # result["projected_balance"] = calculate_total(
    #     "projected_income", "projected_expenses"
    # )

    return render(
        request,
        "transactions/fragments/monthly_summary.html",
        context={"totals": result},
    )


@login_required
def month_year_picker(request):
    current_month = int(
        request.GET.get("month", timezone.localdate(timezone.now()).month)
    )
    current_year = int(request.GET.get("year", timezone.localdate(timezone.now()).year))

    available_years = Transaction.objects.dates("reference_date", "year", order="ASC")

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


# @login_required
# def monthly_income(request, month: int, year: int):
#     situation = request.GET.get("s", "c")
#
#     income_sum_by_currency = (
#         Transaction.objects.filter(
#             type=Transaction.Type.INCOME,
#             is_paid=True if situation == "c" else False,
#             account__is_asset=False,
#             reference_date__year=year,
#             reference_date__month=month,
#         )
#         .values(
#             "account__currency__name",
#             "account__currency__prefix",
#             "account__currency__suffix",
#             "account__currency__decimal_places",
#         )
#         .annotate(
#             total_amount=Coalesce(
#                 Sum("amount"),
#                 0,
#                 output_field=DecimalField(max_digits=30, decimal_places=18),
#             )
#         )
#         .order_by("account__currency__name")
#     )
#
#     print(income_sum_by_currency)
#
#     return render(
#         request,
#         "transactions/fragments/income.html",
#         context={"income": income_sum_by_currency},
#     )
