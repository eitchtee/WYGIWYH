import decimal
import json

from dateutil.relativedelta import relativedelta
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.common.decorators.htmx import only_htmx
from apps.insights.forms import (
    SingleMonthForm,
    SingleYearForm,
    MonthRangeForm,
    YearRangeForm,
    DateRangeForm,
    CategoryForm,
)
from apps.insights.utils.category_explorer import (
    get_category_sums_by_account,
    get_category_sums_by_currency,
)
from apps.insights.utils.sankey import (
    generate_sankey_data_by_account,
    generate_sankey_data_by_currency,
)
from apps.insights.utils.transactions import get_transactions
from apps.transactions.models import TransactionCategory, Transaction
from apps.insights.utils.category_overview import get_categories_totals


@login_required
@require_http_methods(["GET"])
def index(request):
    date = timezone.localdate(timezone.now())
    month_form = SingleMonthForm(initial={"month": date.replace(day=1)})
    year_form = SingleYearForm(initial={"year": date.replace(day=1)})
    month_range_form = MonthRangeForm(
        initial={
            "month_from": date.replace(day=1),
            "month_to": date.replace(day=1) + relativedelta(months=1),
        }
    )
    year_range_form = YearRangeForm(
        initial={
            "year_from": date.replace(day=1, month=1),
            "year_to": date.replace(day=1, month=1) + relativedelta(years=1),
        }
    )
    date_range_form = DateRangeForm(
        initial={
            "date_from": date,
            "date_to": date + relativedelta(months=1),
        }
    )

    return render(
        request,
        "insights/pages/index.html",
        context={
            "month_form": month_form,
            "year_form": year_form,
            "month_range_form": month_range_form,
            "year_range_form": year_range_form,
            "date_range_form": date_range_form,
        },
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def sankey_by_account(request):
    # Get filtered transactions

    transactions = get_transactions(request)

    # Generate Sankey data
    sankey_data = generate_sankey_data_by_account(transactions)

    return render(
        request,
        "insights/fragments/sankey.html",
        {"sankey_data": sankey_data, "type": "account"},
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def sankey_by_currency(request):
    # Get filtered transactions
    transactions = get_transactions(request)

    # Generate Sankey data
    sankey_data = generate_sankey_data_by_currency(transactions)

    return render(
        request,
        "insights/fragments/sankey.html",
        {"sankey_data": sankey_data, "type": "currency"},
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def category_explorer_index(request):
    category_form = CategoryForm()

    return render(
        request,
        "insights/fragments/category_explorer/index.html",
        {"category_form": category_form},
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def category_sum_by_account(request):
    # Get filtered transactions
    transactions = get_transactions(request, include_silent=True)

    category = request.GET.get("category")

    if category:
        category = TransactionCategory.objects.get(id=category)

        # Generate data
        account_data = get_category_sums_by_account(transactions, category)
    else:
        account_data = get_category_sums_by_account(transactions, category=None)

    return render(
        request,
        "insights/fragments/category_explorer/charts/account.html",
        {"account_data": account_data},
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def category_sum_by_currency(request):
    # Get filtered transactions
    transactions = get_transactions(request, include_silent=True)

    category = request.GET.get("category")

    if category:
        category = TransactionCategory.objects.get(id=category)

        # Generate data
        currency_data = get_category_sums_by_currency(transactions, category)
    else:
        currency_data = get_category_sums_by_currency(transactions, category=None)

    return render(
        request,
        "insights/fragments/category_explorer/charts/currency.html",
        {"currency_data": currency_data},
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def category_overview(request):
    # Get filtered transactions
    transactions = get_transactions(request, include_silent=True)

    total_table = get_categories_totals(
        transactions_queryset=transactions, ignore_empty=False
    )

    return render(
        request,
        "insights/fragments/category_overview/index.html",
        {"total_table": total_table},
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def latest_transactions(request):
    limit = timezone.now() - relativedelta(days=3)
    transactions = Transaction.objects.filter(created_at__gte=limit).order_by("-id")[
        :30
    ]

    return render(
        request,
        "insights/fragments/latest_transactions.html",
        {"transactions": transactions},
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def late_transactions(request):
    now = timezone.localdate(timezone.now())
    transactions = Transaction.objects.filter(is_paid=False, date__lt=now)

    return render(
        request,
        "insights/fragments/late_transactions.html",
        {"transactions": transactions},
    )
