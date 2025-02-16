from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from dateutil.relativedelta import relativedelta

from apps.transactions.models import Transaction
from apps.insights.utils.sankey import (
    generate_sankey_data_by_account,
    generate_sankey_data_by_currency,
)
from apps.insights.forms import (
    SingleMonthForm,
    SingleYearForm,
    MonthRangeForm,
    YearRangeForm,
    DateRangeForm,
)
from apps.common.decorators.htmx import only_htmx
from apps.insights.utils.transactions import get_transactions


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
@require_http_methods(["GET", "POST"])
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
@require_http_methods(["GET", "POST"])
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
