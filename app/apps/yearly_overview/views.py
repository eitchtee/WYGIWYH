from datetime import date
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Sum, F, Value, DecimalField, Q
from django.db.models.expressions import Case, When
from django.db.models.functions import TruncMonth, Coalesce, TruncYear
from django.http import Http404
from django.shortcuts import render, redirect
from django.utils import timezone

from apps.currencies.models import Currency
from apps.currencies.utils.convert import convert
from apps.transactions.models import Transaction


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
    currency_options = Currency.objects.all()

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

    transactions = Transaction.objects.filter(**filter_params).exclude(
        Q(category__mute=True) & ~Q(category=None)
    )

    if month:
        date_trunc = TruncMonth("reference_date")
    else:
        date_trunc = TruncYear("reference_date")

    monthly_data = (
        transactions.annotate(month=date_trunc)
        .values(
            "month",
            "account__currency__code",
            "account__currency__prefix",
            "account__currency__suffix",
            "account__currency__decimal_places",
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
                output_field=DecimalField(),
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
                output_field=DecimalField(),
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
                output_field=DecimalField(),
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
                output_field=DecimalField(),
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

    # Create a dictionary to store the final result
    result = {
        "income_paid": [],
        "expense_paid": [],
        "income_unpaid": [],
        "expense_unpaid": [],
        "balance_unpaid": [],
        "balance_paid": [],
        "balance_total": [],
    }

    # Fill in the data
    for entry in monthly_data:
        currency_code = entry["account__currency__code"]
        prefix = entry["account__currency__prefix"]
        suffix = entry["account__currency__suffix"]
        decimal_places = entry["account__currency__decimal_places"]

        for field in [
            "income_paid",
            "expense_paid",
            "income_unpaid",
            "expense_unpaid",
            "balance_unpaid",
            "balance_paid",
            "balance_total",
        ]:
            if entry[field] != 0:
                result[field].append(
                    {
                        "code": currency_code,
                        "prefix": prefix,
                        "suffix": suffix,
                        "decimal_places": decimal_places,
                        "amount": entry[field],
                    }
                )

    print(result)

    return render(
        request,
        "yearly_overview/fragments/currency_data.html",
        context={
            "year": year,
            "totals": result,
        },
    )


@login_required
def yearly_overview_by_account(request, year: int):
    next_year = year + 1
    previous_year = year - 1

    transactions = Transaction.objects.filter(
        reference_date__year=year, account__is_archived=False
    )

    monthly_data = (
        transactions.annotate(month=TruncMonth("reference_date"))
        .select_related(
            "account__currency",
            "account__exchange_currency",
        )
        .values(
            "month",
            "account__id",
            "account__name",
            "account__currency",
            "account__exchange_currency",
            "account__currency__code",
            "account__currency__prefix",
            "account__currency__suffix",
            "account__currency__decimal_places",
            "account__exchange_currency__code",
            "account__exchange_currency__prefix",
            "account__exchange_currency__suffix",
            "account__exchange_currency__decimal_places",
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
                output_field=DecimalField(),
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
                output_field=DecimalField(),
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
                output_field=DecimalField(),
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
                output_field=DecimalField(),
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
        .order_by("month", "account__name")
    )

    all_months = [date(year, month, 1) for month in range(1, 13)]

    # Get all accounts with their currencies
    accounts = (
        transactions.values(
            "account__id",
            "account__name",
            "account__group__name",
            "account__currency__code",
            "account__currency__prefix",
            "account__currency__suffix",
            "account__currency__decimal_places",
            "account__exchange_currency__code",
            "account__exchange_currency__prefix",
            "account__exchange_currency__suffix",
            "account__exchange_currency__decimal_places",
        )
        .distinct()
        .order_by("account__name")
    )

    # Get Currency objects for conversion
    currencies = {currency.id: currency for currency in Currency.objects.all()}

    result = {
        month: {
            account["account__id"]: {
                "name": account["account__name"],
                "group": account["account__group__name"],
                "currency": {
                    "code": account["account__currency__code"],
                    "prefix": account["account__currency__prefix"],
                    "suffix": account["account__currency__suffix"],
                    "decimal_places": account["account__currency__decimal_places"],
                },
                "exchange_currency": (
                    {
                        "code": account["account__exchange_currency__code"],
                        "prefix": account["account__exchange_currency__prefix"],
                        "suffix": account["account__exchange_currency__suffix"],
                        "decimal_places": account[
                            "account__exchange_currency__decimal_places"
                        ],
                    }
                    if account["account__exchange_currency__code"]
                    else None
                ),
                "income_paid": Decimal("0"),
                "expense_paid": Decimal("0"),
                "income_unpaid": Decimal("0"),
                "expense_unpaid": Decimal("0"),
                "balance_unpaid": Decimal("0"),
                "balance_paid": Decimal("0"),
                "balance_total": Decimal("0"),
            }
            for account in accounts
        }
        for month in all_months
    }

    # Fill in the data
    for entry in monthly_data:
        month = entry["month"]
        account_id = entry["account__id"]

        for field in [
            "income_paid",
            "expense_paid",
            "income_unpaid",
            "expense_unpaid",
            "balance_unpaid",
            "balance_paid",
            "balance_total",
        ]:
            result[month][account_id][field] = entry[field]
            if result[month][account_id]["exchange_currency"]:
                from_currency = currencies[entry["account__currency"]]
                to_currency = currencies[entry["account__exchange_currency"]]

                if entry[field] > 0 or entry[field] < 0:
                    converted_amount, prefix, suffix, decimal_places = convert(
                        amount=entry[field],
                        from_currency=from_currency,
                        to_currency=to_currency,
                    )

                    if isinstance(converted_amount, Decimal):
                        print(converted_amount)
                        result[month][account_id][
                            f"exchange_{field}"
                        ] = converted_amount
                else:
                    result[month][account_id][f"exchange_{field}"] = Decimal(0)

    return render(
        request,
        "yearly_overview/pages/overview_by_account.html",
        context={
            "year": year,
            "next_year": next_year,
            "previous_year": previous_year,
            "totals": result,
        },
    )
