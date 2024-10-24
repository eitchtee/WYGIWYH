from datetime import date
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.utils import timezone
from django.db.models import Sum, F, Q, Value, CharField, DecimalField
from django.db.models.functions import TruncMonth, Coalesce
from django.db.models.expressions import Case, When
from django.db.models.functions import Concat

from apps.transactions.models import Transaction


@login_required
def index(request):
    now = timezone.localdate(timezone.now())

    return redirect(to="yearly_overview", year=now.year)


def yearly_overview(request, year: int):
    next_year = year + 1
    previous_year = year - 1

    transactions = Transaction.objects.filter(reference_date__year=year)

    monthly_data = (
        transactions.annotate(month=TruncMonth("reference_date"))
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

    # Create a list of all months in the year
    all_months = [date(year, month, 1) for month in range(1, 13)]

    # Create a dictionary to store the final result
    result = {
        month: {
            "income_paid": [],
            "expense_paid": [],
            "income_unpaid": [],
            "expense_unpaid": [],
            "balance_unpaid": [],
            "balance_paid": [],
            "balance_total": [],
        }
        for month in all_months
    }

    # Fill in the data
    for entry in monthly_data:
        month = entry["month"]
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
                result[month][field].append(
                    {
                        "code": currency_code,
                        "prefix": prefix,
                        "suffix": suffix,
                        "decimal_places": decimal_places,
                        "amount": entry[field],
                    }
                )

    # Fill in missing months with empty lists
    for month in all_months:
        if not any(result[month].values()):
            result[month] = {
                "income_paid": [],
                "expense_paid": [],
                "income_unpaid": [],
                "expense_unpaid": [],
                "balance_unpaid": [],
                "balance_paid": [],
                "balance_total": [],
            }

    return render(
        request,
        "yearly_overview/pages/overview.html",
        context={
            "year": year,
            "next_year": next_year,
            "previous_year": previous_year,
            "totals": result,
        },
    )
