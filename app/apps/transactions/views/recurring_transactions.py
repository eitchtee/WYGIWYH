from dateutil.relativedelta import relativedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.common.decorators.htmx import only_htmx
from apps.transactions.forms import RecurringTransactionForm
from apps.transactions.models import RecurringTransaction
from apps.transactions.tasks import generate_recurring_transactions


@login_required
@require_http_methods(["GET"])
def recurring_transactions_index(request):
    return render(
        request,
        "recurring_transactions/pages/index.html",
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def recurring_transactions_list(request):
    return render(
        request,
        "recurring_transactions/fragments/list.html",
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def active_recurring_transactions_list(request):
    today = timezone.localdate(timezone.now())
    recurring_transactions = RecurringTransaction.objects.filter(
        Q(end_date__gte=today) | Q(end_date__isnull=True),
        is_paused=False,
    ).order_by("-start_date", "description", "id")

    return render(
        request,
        "recurring_transactions/fragments/table.html",
        {"recurring_transactions": recurring_transactions, "status": "active"},
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def paused_recurring_transactions_list(request):
    today = timezone.localdate(timezone.now())
    recurring_transactions = RecurringTransaction.objects.filter(
        Q(end_date__gte=today) | Q(end_date__isnull=True),
        is_paused=True,
    ).order_by("-start_date", "description", "id")

    return render(
        request,
        "recurring_transactions/fragments/table.html",
        {"recurring_transactions": recurring_transactions, "status": "paused"},
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def finished_recurring_transactions_list(request):
    today = timezone.localdate(timezone.now())
    recurring_transactions = RecurringTransaction.objects.filter(
        Q(end_date__lte=today),
    ).order_by("-start_date", "description", "id")

    return render(
        request,
        "recurring_transactions/fragments/table.html",
        {"recurring_transactions": recurring_transactions, "status": "finished"},
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def recurring_transaction_transactions(request, recurring_transaction_id):
    recurring_transaction = get_object_or_404(
        RecurringTransaction, id=recurring_transaction_id
    )
    transactions = recurring_transaction.transactions.all().order_by(
        "reference_date", "id"
    )

    return render(
        request,
        "recurring_transactions/fragments/list_transactions.html",
        {"recurring_transaction": recurring_transaction, "transactions": transactions},
    )


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def recurring_transaction_add(request):
    if request.method == "POST":
        form = RecurringTransactionForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("Recurring Transaction added successfully"))

            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": "updated, hide_offcanvas, toasts",
                },
            )
    else:
        form = RecurringTransactionForm()

    return render(
        request,
        "recurring_transactions/fragments/add.html",
        {"form": form},
    )


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def recurring_transaction_edit(request, recurring_transaction_id):
    recurring_transaction = get_object_or_404(
        RecurringTransaction, id=recurring_transaction_id
    )

    if request.method == "POST":
        form = RecurringTransactionForm(request.POST, instance=recurring_transaction)
        if form.is_valid():
            form.save()
            messages.success(request, _("Recurring Transaction updated successfully"))

            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": "updated, hide_offcanvas, toasts",
                },
            )
    else:
        form = RecurringTransactionForm(instance=recurring_transaction)

    return render(
        request,
        "recurring_transactions/fragments/edit.html",
        {"form": form, "recurring_transaction": recurring_transaction},
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def recurring_transaction_toggle_pause(request, recurring_transaction_id):
    recurring_transaction = get_object_or_404(
        RecurringTransaction, id=recurring_transaction_id
    )
    current_paused = recurring_transaction.is_paused
    recurring_transaction.is_paused = not current_paused
    recurring_transaction.save(update_fields=["is_paused"])

    if current_paused:
        messages.success(request, _("Recurring transaction unpaused successfully"))
        generate_recurring_transactions.defer()
    else:
        messages.success(request, _("Recurring transaction paused successfully"))

    return HttpResponse(
        status=204,
        headers={
            "HX-Trigger": "updated, hide_offcanvas, toasts",
        },
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def recurring_transaction_finish(request, recurring_transaction_id):
    recurring_transaction = get_object_or_404(
        RecurringTransaction, id=recurring_transaction_id
    )
    today = timezone.localdate(timezone.now()) - relativedelta(days=1)

    recurring_transaction.end_date = today
    recurring_transaction.is_paused = True
    recurring_transaction.save(update_fields=["end_date", "is_paused"])

    messages.success(request, _("Recurring transaction finished successfully"))

    return HttpResponse(
        status=204,
        headers={
            "HX-Trigger": "updated, hide_offcanvas, toasts",
        },
    )


@only_htmx
@login_required
@csrf_exempt
@require_http_methods(["DELETE"])
def recurring_transaction_delete(request, recurring_transaction_id):
    recurring_transaction = get_object_or_404(
        RecurringTransaction, id=recurring_transaction_id
    )

    recurring_transaction.delete()

    messages.success(request, _("Recurring Transaction deleted successfully"))

    return HttpResponse(
        status=204,
        headers={
            "HX-Trigger": "updated, hide_offcanvas, toasts",
        },
    )
