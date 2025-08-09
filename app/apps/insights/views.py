from collections import defaultdict

from dateutil.relativedelta import relativedelta
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
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
from apps.insights.utils.category_overview import get_categories_totals
from apps.insights.utils.sankey import (
    generate_sankey_data_by_account,
    generate_sankey_data_by_currency,
)
from apps.insights.utils.transactions import get_transactions
from apps.transactions.models import TransactionCategory, Transaction
from apps.transactions.utils.calculations import calculate_currency_totals


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

    transactions = get_transactions(request, include_untracked_accounts=True)

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
    if "view_type" in request.GET:
        view_type = request.GET["view_type"]
        request.session["insights_category_explorer_view_type"] = view_type
    else:
        view_type = request.session.get("insights_category_explorer_view_type", "table")

    if "show_tags" in request.GET:
        show_tags = request.GET["show_tags"] == "on"
        request.session["insights_category_explorer_show_tags"] = show_tags
    else:
        show_tags = request.session.get("insights_category_explorer_show_tags", True)

    if "showing" in request.GET:
        showing = request.GET["showing"]
        request.session["insights_category_explorer_showing"] = showing
    else:
        showing = request.session.get("insights_category_explorer_showing", "final")

    # Get filtered transactions
    transactions = get_transactions(request, include_silent=True)

    total_table = get_categories_totals(
        transactions_queryset=transactions, ignore_empty=False
    )

    return render(
        request,
        "insights/fragments/category_overview/index.html",
        {
            "total_table": total_table,
            "view_type": view_type,
            "show_tags": show_tags,
            "showing": showing,
        },
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


@only_htmx
@login_required
@require_http_methods(["GET"])
def emergency_fund(request):
    transactions_currency_queryset = (
        Transaction.objects.filter(
            is_paid=True, account__is_archived=False, account__is_asset=False
        )
        .exclude(account__in=request.user.untracked_accounts.all())
        .order_by(
            "account__currency__name",
        )
    )
    currency_net_worth = calculate_currency_totals(
        transactions_queryset=transactions_currency_queryset, ignore_empty=False
    )

    end_date = (timezone.now() - relativedelta(months=1)).replace(day=1)
    start_date = (end_date - relativedelta(months=12)).replace(day=1)

    # Step 1: Calculate total expense for each month and currency
    monthly_expenses = (
        Transaction.objects.filter(
            type=Transaction.Type.EXPENSE,
            is_paid=True,
            account__is_asset=False,
            reference_date__gte=start_date,
            reference_date__lte=end_date,
            category__mute=False,
            mute=False,
        )
        .exclude(account__in=request.user.untracked_accounts.all())
        .values("reference_date", "account__currency")
        .annotate(monthly_total=Sum("amount"))
    )

    # Step 2: Calculate averages by currency using Python
    currency_totals = defaultdict(list)
    for expense in monthly_expenses:
        currency_id = expense["account__currency"]
        currency_totals[currency_id].append(expense["monthly_total"])

    for currency_id, totals in currency_totals.items():
        avg = currency_net_worth[currency_id]["average"] = sum(totals) / len(totals)
        if currency_net_worth[currency_id]["total_current"] < 0:
            currency_net_worth[currency_id]["months"] = 0
        else:
            currency_net_worth[currency_id]["months"] = int(
                currency_net_worth[currency_id]["total_current"] / avg
            )

    return render(
        request,
        "insights/fragments/emergency_fund.html",
        {"data": currency_net_worth},
    )
