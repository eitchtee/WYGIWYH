from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.forms import model_to_dict
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from apps.common.decorators.htmx import only_htmx
from apps.transactions.forms import QuickTransactionForm
from apps.transactions.models import QuickTransaction, transaction_created
from apps.transactions.models import Transaction


@login_required
@require_http_methods(["GET"])
def quick_transactions_index(request):
    return render(
        request,
        "quick_transactions/pages/index.html",
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def quick_transactions_list(request):
    quick_transactions = QuickTransaction.objects.all().order_by("name")
    return render(
        request,
        "quick_transactions/fragments/list.html",
        context={"quick_transactions": quick_transactions},
    )


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def quick_transaction_add(request):
    if request.method == "POST":
        form = QuickTransactionForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("Item added successfully"))

            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": "updated, hide_offcanvas",
                },
            )
    else:
        form = QuickTransactionForm()

    return render(
        request,
        "quick_transactions/fragments/add.html",
        {"form": form},
    )


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def quick_transaction_edit(request, quick_transaction_id):
    quick_transaction = get_object_or_404(QuickTransaction, id=quick_transaction_id)

    if request.method == "POST":
        form = QuickTransactionForm(request.POST, instance=quick_transaction)
        if form.is_valid():
            form.save()
            messages.success(request, _("Item updated successfully"))

            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": "updated, hide_offcanvas",
                },
            )
    else:
        form = QuickTransactionForm(instance=quick_transaction)

    return render(
        request,
        "quick_transactions/fragments/edit.html",
        {"form": form, "quick_transaction": quick_transaction},
    )


@only_htmx
@login_required
@require_http_methods(["DELETE"])
def quick_transaction_delete(request, quick_transaction_id):
    quick_transaction = get_object_or_404(QuickTransaction, id=quick_transaction_id)

    quick_transaction.delete()

    messages.success(request, _("Item deleted successfully"))

    return HttpResponse(
        status=204,
        headers={
            "HX-Trigger": "updated, hide_offcanvas",
        },
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def quick_transactions_create_menu(request):
    quick_transactions = QuickTransaction.objects.all().order_by("name")
    return render(
        request,
        "quick_transactions/fragments/create_menu.html",
        context={"quick_transactions": quick_transactions},
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def quick_transaction_add_as_transaction(request, quick_transaction_id):
    quick_transaction: QuickTransaction = get_object_or_404(
        QuickTransaction, id=quick_transaction_id
    )
    today = timezone.localdate(timezone.now())

    quick_transaction_data = model_to_dict(
        quick_transaction,
        exclude=[
            "id",
            "name",
            "owner",
            "account",
            "category",
            "tags",
            "entities",
        ],
    )

    new_transaction = Transaction(**quick_transaction_data)
    new_transaction.account = quick_transaction.account
    new_transaction.category = quick_transaction.category

    new_transaction.date = today
    new_transaction.reference_date = today.replace(day=1)
    new_transaction.save()
    new_transaction.tags.set(quick_transaction.tags.all())
    new_transaction.entities.set(quick_transaction.entities.all())

    transaction_created.send(sender=new_transaction)

    messages.success(request, _("Transaction added successfully"))

    return HttpResponse(
        status=204,
        headers={
            "HX-Trigger": "updated, hide_offcanvas",
        },
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def quick_transaction_add_as_quick_transaction(request, transaction_id):
    transaction: Transaction = get_object_or_404(Transaction, pk=transaction_id)

    if (
        transaction.description
        and QuickTransaction.objects.filter(
            name__startswith=transaction.description
        ).exists()
    ) or QuickTransaction.objects.filter(
        name__startswith=_("Quick Transaction")
    ).exists():
        if transaction.description:
            count = QuickTransaction.objects.filter(
                name__startswith=transaction.description
            ).count()
            qt_name = transaction.description + f" ({count + 1})"
        else:
            count = QuickTransaction.objects.filter(
                name__startswith=_("Quick Transaction")
            ).count()
            qt_name = _("Quick Transaction") + f" ({count + 1})"
    else:
        qt_name = transaction.description or _("Quick Transaction")

    transaction_data = model_to_dict(
        transaction,
        exclude=[
            "id",
            "name",
            "owner",
            "account",
            "category",
            "tags",
            "entities",
            "date",
            "reference_date",
            "installment_plan",
            "installment_id",
            "recurring_transaction",
            "deleted",
            "deleted_at",
        ],
    )

    new_quick_transaction = QuickTransaction(**transaction_data)
    new_quick_transaction.account = transaction.account
    new_quick_transaction.category = transaction.category

    new_quick_transaction.name = qt_name

    new_quick_transaction.save()
    new_quick_transaction.tags.set(transaction.tags.all())
    new_quick_transaction.entities.set(transaction.entities.all())

    messages.success(request, _("Item added successfully"))

    return HttpResponse(
        status=204,
        headers={
            "HX-Trigger": "toasts",
        },
    )
