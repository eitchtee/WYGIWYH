import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.common.decorators.htmx import only_htmx
from apps.transactions.forms import TransactionForm, TransferForm, InstallmentPlanForm
from apps.transactions.models import Transaction


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
        form = TransactionForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("Transaction added successfully"))

            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "updated, hide_offcanvas, toast"},
            )
    else:
        form = TransactionForm(
            initial={
                "date": expected_date,
                "type": transaction_type,
            }
        )

    return render(
        request,
        "transactions/fragments/add.html",
        {"form": form},
    )


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def transaction_edit(request, transaction_id, **kwargs):
    transaction = get_object_or_404(Transaction, id=transaction_id)

    if request.method == "POST":
        form = TransactionForm(request.POST, instance=transaction)
        if form.is_valid():
            form.save()
            messages.success(request, _("Transaction updated successfully"))

            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "updated, hide_offcanvas, toast"},
            )
    else:
        form = TransactionForm(instance=transaction)

    return render(
        request,
        "transactions/fragments/edit.html",
        {"form": form, "transaction": transaction},
    )


@only_htmx
@login_required
@csrf_exempt
@require_http_methods(["DELETE"])
def transaction_delete(request, transaction_id, **kwargs):
    transaction = get_object_or_404(Transaction, id=transaction_id)

    transaction.delete()

    messages.success(request, _("Transaction deleted successfully"))

    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "updated, toast"},
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
        form = TransferForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("Transfer added successfully"))
            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "updated, toast, hide_offcanvas"},
            )
    else:
        form = TransferForm(
            initial={
                "reference_date": expected_date,
                "date": expected_date,
            }
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
        f'{"paid" if new_is_paid else "unpaid"}, monthly_summary_update'
    )
    return response
