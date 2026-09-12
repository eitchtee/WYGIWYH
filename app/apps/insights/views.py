from collections import defaultdict

from dateutil.relativedelta import relativedelta
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
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
from apps.insights.utils.overview import get_grouped_totals
from apps.insights.utils.sankey import (
    generate_sankey_data_by_account,
    generate_sankey_data_by_currency,
)
from apps.insights.utils.transactions import get_transactions
from apps.insights.utils.year_by_year import get_year_by_year_data
from apps.insights.utils.month_by_month import get_month_by_month_data
from apps.transactions.models import TransactionCategory, Transaction
from apps.transactions.utils.calculations import calculate_currency_totals

# Labels for the grouping levels an overview can be built from. The overviews
# only differ by which level sits at the top, so everything user facing lives
# here instead of in three near identical views and templates.
OVERVIEW_LEVELS = {
    "categories": {
        "label": _("Categories"),
        "singular": _("Category"),
        "empty": _("Uncategorized"),
        "empty_message": _("No categories"),
        "icon": "fa-solid fa-icons",
    },
    "tags": {
        "label": _("Tags"),
        "singular": _("Tag"),
        "empty": _("Untagged"),
        "empty_message": _("No tags"),
        "icon": "fa-solid fa-hashtag",
    },
    "entities": {
        "label": _("Entities"),
        "singular": _("Entity"),
        "empty": _("No entity"),
        "empty_message": _("No entities"),
        "icon": "fa-solid fa-user-group",
    },
}


def _render_overview(request, levels, url_name):
    """Render the overview table/chart for ``levels``, top level first."""
    session_prefix = f"insights_{levels[0]}_overview"

    def setting(name, default, cast=None):
        key = f"{session_prefix}_{name}"
        if name in request.GET:
            value = cast(request.GET[name]) if cast else request.GET[name]
            request.session[key] = value
            return value
        return request.session.get(key, default)

    view_type = setting("view_type", "table")
    showing = setting("showing", "final")
    show_level_2 = setting("show_level_2", True, cast=lambda value: value == "on")
    show_level_3 = setting("show_level_3", False, cast=lambda value: value == "on")

    if show_level_2:
        depth = 3 if show_level_3 else 2
    else:
        depth = 1

    total_table = get_grouped_totals(
        transactions_queryset=get_transactions(request, include_silent=True),
        levels=levels,
        showing=showing,
        ignore_empty=False,
        depth=depth,
    )

    return render(
        request,
        "insights/fragments/overview/index.html",
        {
            "total_table": total_table,
            "refresh_url": reverse(url_name),
            "view_type": view_type,
            "showing": showing,
            "show_level_2": show_level_2,
            "show_level_3": show_level_3,
            "level_1": OVERVIEW_LEVELS[levels[0]],
            "level_2": OVERVIEW_LEVELS[levels[1]],
            "level_3": OVERVIEW_LEVELS[levels[2]],
            "empty_message": OVERVIEW_LEVELS[levels[0]]["empty_message"],
        },
    )


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

    transactions = get_transactions(
        request, include_untracked_accounts=True, include_silent=True
    )

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
    transactions = get_transactions(
        request, include_silent=True, include_untracked_accounts=True
    )

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
    return _render_overview(
        request, ("categories", "tags", "entities"), "category_overview"
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def tag_overview(request):
    return _render_overview(request, ("tags", "categories", "entities"), "tag_overview")


@only_htmx
@login_required
@require_http_methods(["GET"])
def entity_overview(request):
    return _render_overview(
        request, ("entities", "categories", "tags"), "entity_overview"
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


@only_htmx
@login_required
@require_http_methods(["GET"])
def year_by_year(request):
    if "group_by" in request.GET:
        group_by = request.GET["group_by"]
        request.session["insights_year_by_year_group_by"] = group_by
    else:
        group_by = request.session.get("insights_year_by_year_group_by", "categories")

    # Validate group_by value
    if group_by not in ("categories", "tags", "entities"):
        group_by = "categories"

    data = get_year_by_year_data(group_by=group_by)

    return render(
        request,
        "insights/fragments/year_by_year.html",
        {
            "data": data,
            "group_by": group_by,
        },
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def month_by_month(request):
    # Handle year selection
    if "year" in request.GET:
        try:
            year = int(request.GET["year"])
            request.session["insights_month_by_month_year"] = year
        except (ValueError, TypeError):
            year = request.session.get(
                "insights_month_by_month_year", timezone.localdate(timezone.now()).year
            )
    else:
        year = request.session.get(
            "insights_month_by_month_year", timezone.localdate(timezone.now()).year
        )

    # Handle group_by selection
    if "group_by" in request.GET:
        group_by = request.GET["group_by"]
        request.session["insights_month_by_month_group_by"] = group_by
    else:
        group_by = request.session.get("insights_month_by_month_group_by", "categories")

    # Validate group_by value
    if group_by not in ("categories", "tags", "entities"):
        group_by = "categories"

    data = get_month_by_month_data(year=year, group_by=group_by)

    return render(
        request,
        "insights/fragments/month_by_month.html",
        {
            "data": data,
            "group_by": group_by,
            "selected_year": year,
        },
    )
