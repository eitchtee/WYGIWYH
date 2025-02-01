from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import Http404
from django.shortcuts import render, redirect
from django.utils import timezone

from apps.accounts.models import Account
from apps.common.decorators.htmx import only_htmx
from apps.common.utils.dicts import remove_falsey_entries
from apps.currencies.models import Currency
from apps.transactions.models import Transaction
from apps.transactions.utils.calculations import (
    calculate_account_totals,
    calculate_currency_totals,
    calculate_percentage_distribution,
)


@login_required
def index_by_currency(request):
    now = timezone.localdate(timezone.now())

    return redirect(to="yearly_overview_currency", year=now.year)


@login_required
def index_by_account(request):
    now = timezone.localdate(timezone.now())

    return redirect(to="yearly_overview_account", year=now.year)


@login_required
def index_yearly_overview_by_currency(request, year: int):
    next_year = year + 1
    previous_year = year - 1

    month_options = range(1, 13)
    currency_options = Currency.objects.filter(
        accounts__transactions__date__year=year
    ).distinct()

    return render(
        request,
        "yearly_overview/pages/overview_by_currency.html",
        context={
            "year": year,
            "next_year": next_year,
            "previous_year": previous_year,
            "months": month_options,
            "currencies": currency_options,
        },
    )


@only_htmx
@login_required
def yearly_overview_by_currency(request, year: int):
    month = request.GET.get("month")
    currency = request.GET.get("currency")

    # Base query filter
    filter_params = {"reference_date__year": year, "account__is_archived": False}

    # Add month filter if provided
    if month:
        month = int(month)
        if not 1 <= month <= 12:
            raise Http404("Invalid month")
        filter_params["reference_date__month"] = month

    # Add currency filter if provided
    if currency:
        filter_params["account__currency_id"] = int(currency)

    transactions = (
        Transaction.objects.filter(**filter_params)
        .exclude(Q(category__mute=True) & ~Q(category=None))
        .order_by("account__currency__name")
    )

    data = calculate_currency_totals(transactions)
    percentages = calculate_percentage_distribution(data)

    return render(
        request,
        "yearly_overview/fragments/currency_data.html",
        context={
            "year": year,
            "totals": data,
            "percentages": percentages,
        },
    )


@login_required
def index_yearly_overview_by_account(request, year: int):
    next_year = year + 1
    previous_year = year - 1

    month_options = range(1, 13)
    account_options = (
        Account.objects.filter(is_archived=False, transactions__date__year=year)
        .select_related("group")
        .distinct()
        .order_by("group__name", "name", "id")
    )

    return render(
        request,
        "yearly_overview/pages/overview_by_account.html",
        context={
            "year": year,
            "next_year": next_year,
            "previous_year": previous_year,
            "months": month_options,
            "accounts": account_options,
        },
    )


@only_htmx
@login_required
def yearly_overview_by_account(request, year: int):
    month = request.GET.get("month")
    account = request.GET.get("account")

    # Base query filter
    filter_params = {"reference_date__year": year, "account__is_archived": False}

    # Add month filter if provided
    if month:
        month = int(month)
        if not 1 <= month <= 12:
            raise Http404("Invalid month")
        filter_params["reference_date__month"] = month

    # Add account filter if provided
    if account:
        filter_params["account_id"] = int(account)

    transactions = (
        Transaction.objects.filter(**filter_params)
        .exclude(Q(category__mute=True) & ~Q(category=None))
        .order_by(
            "account__group__name",
            "account__name",
        )
    )

    data = calculate_account_totals(transactions)
    percentages = calculate_percentage_distribution(data)

    return render(
        request,
        "yearly_overview/fragments/account_data.html",
        context={
            "year": year,
            "totals": data,
            "percentages": percentages,
        },
    )
