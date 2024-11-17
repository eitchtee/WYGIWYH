from datetime import date
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Sum, F, Value, DecimalField, Q
from django.db.models.expressions import Case, When
from django.db.models.functions import TruncMonth, Coalesce, TruncYear
from django.http import Http404
from django.shortcuts import render, redirect
from django.utils import timezone

from apps.accounts.models import Account
from apps.currencies.models import Currency
from apps.currencies.utils.convert import convert
from apps.transactions.models import Transaction
from apps.common.decorators.htmx import only_htmx
from apps.transactions.utils.calculations import calculate_account_totals


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
        .select_related("account__currency")  # Optimize by pre-fetching currency data
    )

    date_trunc = TruncMonth("reference_date") if month else TruncYear("reference_date")

    monthly_data = (
        transactions.annotate(month=date_trunc)
        .values(
            "month",
            "account__currency__code",
            "account__currency__prefix",
            "account__currency__suffix",
            "account__currency__decimal_places",
            "account__currency_id",
            "account__currency__exchange_currency_id",
        )
        .annotate(
            income_paid=Coalesce(
                Sum(
                    Case(
                        When(
                            type=Transaction.Type.INCOME, is_paid=True, then=F("amount")
                        ),
                        default=Value(Decimal("0")),
                        output_field=DecimalField(),
                    )
                ),
                Value(Decimal("0")),
            ),
            expense_paid=Coalesce(
                Sum(
                    Case(
                        When(
                            type=Transaction.Type.EXPENSE,
                            is_paid=True,
                            then=F("amount"),
                        ),
                        default=Value(Decimal("0")),
                        output_field=DecimalField(),
                    )
                ),
                Value(Decimal("0")),
            ),
            income_unpaid=Coalesce(
                Sum(
                    Case(
                        When(
                            type=Transaction.Type.INCOME,
                            is_paid=False,
                            then=F("amount"),
                        ),
                        default=Value(Decimal("0")),
                        output_field=DecimalField(),
                    )
                ),
                Value(Decimal("0")),
            ),
            expense_unpaid=Coalesce(
                Sum(
                    Case(
                        When(
                            type=Transaction.Type.EXPENSE,
                            is_paid=False,
                            then=F("amount"),
                        ),
                        default=Value(Decimal("0")),
                        output_field=DecimalField(),
                    )
                ),
                Value(Decimal("0")),
            ),
        )
        .annotate(
            balance_unpaid=F("income_unpaid") - F("expense_unpaid"),
            balance_paid=F("income_paid") - F("expense_paid"),
            balance_total=F("income_paid")
            + F("income_unpaid")
            - F("expense_paid")
            - F("expense_unpaid"),
        )
        .order_by("month", "account__currency__code")
    )

    # Fetch all currencies and their exchange currencies in a single query
    currencies = {
        currency.id: currency
        for currency in Currency.objects.select_related("exchange_currency").all()
    }

    result = {
        "income_paid": [],
        "expense_paid": [],
        "income_unpaid": [],
        "expense_unpaid": [],
        "balance_unpaid": [],
        "balance_paid": [],
        "balance_total": [],
    }

    for entry in monthly_data:
        if all(entry[field] == 0 for field in result.keys()):
            continue  # Skip entries where all values are 0

        currency_code = entry["account__currency__code"]
        prefix = entry["account__currency__prefix"]
        suffix = entry["account__currency__suffix"]
        decimal_places = entry["account__currency__decimal_places"]

        # Get the currency objects for conversion
        from_currency = currencies.get(entry["account__currency_id"])
        to_currency = (
            None
            if not from_currency
            else currencies.get(from_currency.exchange_currency_id)
        )

        for field in result.keys():
            amount = entry[field]
            if amount == 0:
                continue

            item = {
                "code": currency_code,
                "prefix": prefix,
                "suffix": suffix,
                "decimal_places": decimal_places,
                "amount": amount,
                "exchanged": None,
            }

            # Add exchange calculation if possible
            if from_currency and to_currency:
                exchanged_amount, ex_prefix, ex_suffix, ex_decimal_places = convert(
                    amount=amount,
                    from_currency=from_currency,
                    to_currency=to_currency,
                )
                item["exchanged"] = {
                    "amount": exchanged_amount,
                    "code": to_currency.code,
                    "prefix": ex_prefix,
                    "suffix": ex_suffix,
                    "decimal_places": ex_decimal_places,
                }

            result[field].append(item)

    return render(
        request,
        "yearly_overview/fragments/currency_data.html",
        context={
            "year": year,
            "totals": result,
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

    transactions = Transaction.objects.filter(**filter_params).order_by(
        "account__group__name", "account__name", "id"
    )

    data = calculate_account_totals(transactions)

    from pprint import pprint

    pprint(data)

    return render(
        request,
        "yearly_overview/fragments/account_data.html",
        context={"year": year, "totals": data, "single": True if account else False},
    )
