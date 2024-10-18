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


# Create your views here.
@login_required
def index(request):
    now = timezone.localdate(timezone.now())

    return redirect(to="yearly_overview", year=now.year)


def yearly_overview(request, year: int):
    transactions = Transaction.objects.filter(date__year=year)

    monthly_data = (
        transactions.annotate(month=TruncMonth("date"))
        .values(
            "month",
            "account__id",
            "account__name",
            "account__group__name",
            "account__currency__code",
            "account__currency__suffix",
            "account__currency__prefix",
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
        .order_by("month", "account__group__name")
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
        account_info = {
            "id": entry["account__id"],
            "name": entry["account__name"],
            "currency": entry["account__currency__code"],
            "suffix": entry["account__currency__suffix"],
            "prefix": entry["account__currency__prefix"],
            "decimal_places": entry["account__currency__decimal_places"],
            "group": entry["account__group__name"],
        }

        for field in [
            "income_paid",
            "expense_paid",
            "income_unpaid",
            "expense_unpaid",
            "balance_unpaid",
            "balance_paid",
            "balance_total",
        ]:
            result[month][field].append(
                {"account": account_info, "amount": entry[field]}
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

    from pprint import pprint

    pprint(result)

    return render(
        request,
        "yearly_overview/pages/overview2.html",
        context={
            "year": year,
            # "next_month": next_month,
            # "next_year": next_year,
            # "previous_month": previous_month,
            # "previous_year": previous_year,
            "data": result,
        },
    )


# def yearly_overview(request, year: int):
#     # First, let's create a base queryset for the given year
#     base_queryset = Transaction.objects.filter(date__year=year)
#
#     # Create a list of all months in the year
#     months = [month for month in range(1, 13)]
#
#     # Create the queryset with all the required annotations
#     queryset = (
#         base_queryset.annotate(month=TruncMonth("date"))
#         .values("month", "account__group__name")
#         .annotate(
#             income_paid=Coalesce(
#                 Sum(
#                     Case(
#                         When(
#                             Q(type=Transaction.Type.INCOME, is_paid=True),
#                             then=F("amount"),
#                         ),
#                         default=Value(0),
#                         output_field=DecimalField(),
#                     )
#                 ),
#                 Value(0, output_field=DecimalField()),
#             ),
#             expense_paid=Coalesce(
#                 Sum(
#                     Case(
#                         When(
#                             Q(type=Transaction.Type.EXPENSE, is_paid=True),
#                             then=F("amount"),
#                         ),
#                         default=Value(0),
#                         output_field=DecimalField(),
#                     )
#                 ),
#                 Value(0, output_field=DecimalField()),
#             ),
#             income_unpaid=Coalesce(
#                 Sum(
#                     Case(
#                         When(
#                             Q(type=Transaction.Type.INCOME, is_paid=False),
#                             then=F("amount"),
#                         ),
#                         default=Value(0),
#                         output_field=DecimalField(),
#                     )
#                 ),
#                 Value(0, output_field=DecimalField()),
#             ),
#             expense_unpaid=Coalesce(
#                 Sum(
#                     Case(
#                         When(
#                             Q(type=Transaction.Type.EXPENSE, is_paid=False),
#                             then=F("amount"),
#                         ),
#                         default=Value(0),
#                         output_field=DecimalField(),
#                     )
#                 ),
#                 Value(0, output_field=DecimalField()),
#             ),
#         )
#         .annotate(
#             balance_unpaid=F("income_unpaid") - F("expense_unpaid"),
#             balance_paid=F("income_paid") - F("expense_paid"),
#             balance_total=F("income_paid")
#             + F("income_unpaid")
#             - F("expense_paid")
#             - F("expense_unpaid"),
#         )
#         .order_by("month", "account__group__name")
#     )
#
#     # Create a dictionary to store results
#     results = {month: {} for month in months}
#     print(results)
#
#     # Populate the results dictionary
#     for entry in queryset:
#         month = int(entry["month"].strftime("%m"))
#         account_group = entry["account__group__name"]
#
#         if account_group not in results[month]:
#             results[month][account_group] = {
#                 "income_paid": entry["income_paid"],
#                 "expense_paid": entry["expense_paid"],
#                 "income_unpaid": entry["income_unpaid"],
#                 "expense_unpaid": entry["expense_unpaid"],
#                 "balance_unpaid": entry["balance_unpaid"],
#                 "balance_paid": entry["balance_paid"],
#                 "balance_total": entry["balance_total"],
#             }
#         else:
#             # If the account group already exists, update the values
#             for key in [
#                 "income_paid",
#                 "expense_paid",
#                 "income_unpaid",
#                 "expense_unpaid",
#                 "balance_unpaid",
#                 "balance_paid",
#                 "balance_total",
#             ]:
#                 results[month][account_group][key] += entry[key]
#
#     # Replace empty months with "-"
#     for month in results:
#         if not results[month]:
#             results[month] = "-"
#
#     from pprint import pprint
#
#     pprint(results)
#
#     return render(
#         request,
#         "yearly_overview/pages/overview2.html",
#         context={
#             "year": year,
#             # "next_month": next_month,
#             # "next_year": next_year,
#             # "previous_month": previous_month,
#             # "previous_year": previous_year,
#             "data": results,
#         },
#     )


# def yearly_overview(request, year: int):
#     transactions = Transaction.objects.filter(reference_date__year=year)
#
#     monthly_data = (
#         transactions.annotate(month=TruncMonth("reference_date"))
#         .values(
#             "month",
#             "account__currency__code",
#             "account__currency__prefix",
#             "account__currency__suffix",
#             "account__currency__decimal_places",
#         )
#         .annotate(
#             income_paid=Coalesce(
#                 Sum(
#                     Case(
#                         When(
#                             type=Transaction.Type.INCOME, is_paid=True, then=F("amount")
#                         ),
#                         default=Value(Decimal("0")),
#                         output_field=DecimalField(),
#                     )
#                 ),
#                 Value(Decimal("0")),
#                 output_field=DecimalField(),
#             ),
#             expense_paid=Coalesce(
#                 Sum(
#                     Case(
#                         When(
#                             type=Transaction.Type.EXPENSE,
#                             is_paid=True,
#                             then=F("amount"),
#                         ),
#                         default=Value(Decimal("0")),
#                         output_field=DecimalField(),
#                     )
#                 ),
#                 Value(Decimal("0")),
#                 output_field=DecimalField(),
#             ),
#             income_unpaid=Coalesce(
#                 Sum(
#                     Case(
#                         When(
#                             type=Transaction.Type.INCOME,
#                             is_paid=False,
#                             then=F("amount"),
#                         ),
#                         default=Value(Decimal("0")),
#                         output_field=DecimalField(),
#                     )
#                 ),
#                 Value(Decimal("0")),
#                 output_field=DecimalField(),
#             ),
#             expense_unpaid=Coalesce(
#                 Sum(
#                     Case(
#                         When(
#                             type=Transaction.Type.EXPENSE,
#                             is_paid=False,
#                             then=F("amount"),
#                         ),
#                         default=Value(Decimal("0")),
#                         output_field=DecimalField(),
#                     )
#                 ),
#                 Value(Decimal("0")),
#                 output_field=DecimalField(),
#             ),
#         )
#         .annotate(
#             balance_unpaid=F("income_unpaid") - F("expense_unpaid"),
#             balance_paid=F("income_paid") - F("expense_paid"),
#             balance_total=F("income_paid")
#             + F("income_unpaid")
#             - F("expense_paid")
#             - F("expense_unpaid"),
#         )
#         .order_by("month", "account__currency__code")
#     )
#
#     # Create a list of all months in the year
#     all_months = [date(year, month, 1) for month in range(1, 13)]
#
#     # Create a dictionary to store the final result
#     result = {
#         month: {
#             "income_paid": [],
#             "expense_paid": [],
#             "income_unpaid": [],
#             "expense_unpaid": [],
#             "balance_unpaid": [],
#             "balance_paid": [],
#             "balance_total": [],
#         }
#         for month in all_months
#     }
#
#     # Fill in the data
#     for entry in monthly_data:
#         month = entry["month"]
#         currency_code = entry["account__currency__code"]
#         prefix = entry["account__currency__prefix"]
#         suffix = entry["account__currency__suffix"]
#         decimal_places = entry["account__currency__decimal_places"]
#
#         for field in [
#             "income_paid",
#             "expense_paid",
#             "income_unpaid",
#             "expense_unpaid",
#             "balance_unpaid",
#             "balance_paid",
#             "balance_total",
#         ]:
#             result[month][field].append(
#                 {
#                     "code": currency_code,
#                     "prefix": prefix,
#                     "suffix": suffix,
#                     "decimal_places": decimal_places,
#                     "amount": entry[field],
#                 }
#             )
#
#     # Fill in missing months with empty lists
#     for month in all_months:
#         if not any(result[month].values()):
#             result[month] = {
#                 "income_paid": [],
#                 "expense_paid": [],
#                 "income_unpaid": [],
#                 "expense_unpaid": [],
#                 "balance_unpaid": [],
#                 "balance_paid": [],
#                 "balance_total": [],
#             }
#
#     from pprint import pprint
#
#     pprint(result)
#
#     return render(
#         request,
#         "yearly_overview/pages/overview.html",
#         context={
#             "year": year,
#             # "next_month": next_month,
#             # "next_year": next_year,
#             # "previous_month": previous_month,
#             # "previous_year": previous_year,
#             "totals": result,
#         },
#     )
