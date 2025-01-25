import datetime
from copy import deepcopy

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from apps.common.decorators.htmx import only_htmx
from apps.common.utils.dicts import remove_falsey_entries
from apps.rules.signals import transaction_created
from apps.transactions.filters import TransactionsFilter
from apps.transactions.forms import TransactionForm, TransferForm
from apps.transactions.models import Transaction
from apps.transactions.utils.calculations import (
    calculate_currency_totals,
    calculate_account_totals,
    calculate_percentage_distribution,
)
from apps.transactions.utils.default_ordering import default_order


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def transaction_add(request):
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
        form = TransactionForm(request.POST, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, _("Transaction added successfully"))

            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "updated, hide_offcanvas"},
            )
    else:
        form = TransactionForm(
            user=request.user,
            initial={
                "date": expected_date,
                "type": transaction_type,
            },
        )

    return render(
        request,
        "transactions/fragments/add.html",
        {"form": form},
    )


@login_required
@require_http_methods(["GET", "POST"])
def transaction_simple_add(request):
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
        form = TransactionForm(request.POST, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, _("Transaction added successfully"))

        form = TransactionForm(
            user=request.user,
            initial={
                "date": expected_date,
                "type": transaction_type,
            },
        )

    else:
        form = TransactionForm(
            user=request.user,
            initial={
                "date": expected_date,
                "type": transaction_type,
            },
        )

    return render(
        request,
        "transactions/pages/add.html",
        {"form": form},
    )


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def transaction_edit(request, transaction_id, **kwargs):
    transaction = get_object_or_404(Transaction, id=transaction_id)

    if request.method == "POST":
        form = TransactionForm(request.POST, user=request.user, instance=transaction)
        if form.is_valid():
            form.save()
            messages.success(request, _("Transaction updated successfully"))

            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "updated, hide_offcanvas"},
            )
    else:
        form = TransactionForm(instance=transaction, user=request.user)

    return render(
        request,
        "transactions/fragments/edit.html",
        {"form": form, "transaction": transaction},
    )


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def transaction_clone(request, transaction_id, **kwargs):
    transaction = get_object_or_404(Transaction, id=transaction_id)
    new_transaction = deepcopy(transaction)
    new_transaction.pk = None
    new_transaction.installment_plan = None
    new_transaction.installment_id = None
    new_transaction.recurring_transaction = None
    new_transaction.save()

    new_transaction.tags.add(*transaction.tags.all())
    new_transaction.entities.add(*transaction.entities.all())

    messages.success(request, _("Transaction duplicated successfully"))

    transaction_created.send(sender=transaction)

    # THIS HAS BEEN DISABLE DUE TO HTMX INCOMPATIBILITY
    # SEE https://github.com/bigskysoftware/htmx/issues/3115 and https://github.com/bigskysoftware/htmx/issues/2706

    # if request.GET.get("edit") == "true":
    #     return HttpResponse(
    #         status=200,
    #         headers={
    #             "HX-Trigger": "updated",
    #             "HX-Push-Url": "false",
    #             "HX-Location": json.dumps(
    #                 {
    #                     "path": reverse(
    #                         "transaction_edit",
    #                         kwargs={"transaction_id": new_transaction.id},
    #                     ),
    #                     "target": "#generic-offcanvas",
    #                     "swap": "innerHTML",
    #                 }
    #             ),
    #         },
    #     )
    # else:
    #     transaction_created.send(sender=transaction)

    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "updated"},
    )


@only_htmx
@login_required
@require_http_methods(["DELETE"])
def transaction_delete(request, transaction_id, **kwargs):
    transaction = get_object_or_404(Transaction, id=transaction_id)

    transaction.delete()

    messages.success(request, _("Transaction deleted successfully"))

    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "updated"},
    )


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def transactions_transfer(request):
    month = int(request.GET.get("month", timezone.localdate(timezone.now()).month))
    year = int(request.GET.get("year", timezone.localdate(timezone.now()).year))

    now = timezone.localdate(timezone.now())
    expected_date = datetime.datetime(
        day=now.day if month == now.month and year == now.year else 1,
        month=month,
        year=year,
    ).date()

    if request.method == "POST":
        form = TransferForm(request.POST, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, _("Transfer added successfully"))
            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "updated, hide_offcanvas"},
            )
    else:
        form = TransferForm(
            initial={
                "reference_date": expected_date,
                "date": expected_date,
            },
            user=request.user,
        )

    return render(request, "transactions/fragments/transfer.html", {"form": form})


@only_htmx
@login_required
@require_http_methods(["GET"])
def transaction_pay(request, transaction_id):
    transaction = get_object_or_404(Transaction, pk=transaction_id)
    new_is_paid = False if transaction.is_paid else True
    transaction.is_paid = new_is_paid
    transaction.save()

    response = render(
        request,
        "transactions/fragments/item.html",
        context={"transaction": transaction, **request.GET},
    )
    response.headers["HX-Trigger"] = (
        f'{"paid" if new_is_paid else "unpaid"}, selective_update'
    )
    return response


@login_required
@require_http_methods(["GET"])
def transaction_all_index(request):
    f = TransactionsFilter(request.GET, user=request.user)
    return render(request, "transactions/pages/transactions.html", {"filter": f})


@only_htmx
@login_required
@require_http_methods(["GET"])
def transaction_all_list(request):
    order = request.GET.get("order")

    transactions = Transaction.objects.prefetch_related(
        "account",
        "account__group",
        "category",
        "tags",
        "account__exchange_currency",
        "account__currency",
        "installment_plan",
    ).all()

    transactions = default_order(transactions, order=order)

    f = TransactionsFilter(request.GET, user=request.user, queryset=transactions)

    page_number = request.GET.get("page", 1)
    paginator = Paginator(f.qs, 100)
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "transactions/fragments/list_all.html",
        {
            "page_obj": page_obj,
            "paginator": paginator,
        },
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def transaction_all_summary(request):
    transactions = Transaction.objects.prefetch_related(
        "account",
        "account__group",
        "category",
        "tags",
        "account__exchange_currency",
        "account__currency",
        "installment_plan",
    ).all()

    f = TransactionsFilter(request.GET, user=request.user, queryset=transactions)

    currency_data = calculate_currency_totals(f.qs.all(), ignore_empty=True)
    currency_percentages = calculate_percentage_distribution(currency_data)
    account_data = calculate_account_totals(transactions_queryset=f.qs.all())
    account_percentages = calculate_percentage_distribution(account_data)

    context = {
        "income_current": remove_falsey_entries(currency_data, "income_current"),
        "income_projected": remove_falsey_entries(currency_data, "income_projected"),
        "expense_current": remove_falsey_entries(currency_data, "expense_current"),
        "expense_projected": remove_falsey_entries(currency_data, "expense_projected"),
        "total_current": remove_falsey_entries(currency_data, "total_current"),
        "total_final": remove_falsey_entries(currency_data, "total_final"),
        "total_projected": remove_falsey_entries(currency_data, "total_projected"),
        "currency_percentages": currency_percentages,
        "account_data": account_data,
        "account_percentages": account_percentages,
    }

    return render(request, "transactions/fragments/summary.html", context)
