import json
from copy import deepcopy

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse
from django.utils.translation import gettext_lazy as _, ngettext_lazy

from apps.common.decorators.htmx import only_htmx
from apps.transactions.models import Transaction
from apps.rules.signals import transaction_updated


def _selected(manager, request):
    """Selected transactions plus the other side of any selected transfer."""
    ids = request.GET.getlist("transactions", [])
    return manager.filter(Q(id__in=ids) | Q(linked_transaction_id__in=ids))


def _copy(transaction):
    new_transaction = deepcopy(transaction)
    new_transaction.pk = None
    new_transaction.installment_plan = None
    new_transaction.installment_id = None
    new_transaction.recurring_transaction = None
    new_transaction.internal_id = None
    new_transaction.linked_transaction = None
    new_transaction.save()

    new_transaction.tags.add(*transaction.tags.all())
    new_transaction.entities.add(*transaction.entities.all())
    return new_transaction


def clone_transaction(transaction):
    """Duplicates a transaction, or both sides of a transfer."""
    new_transaction = _copy(transaction)
    if transaction.linked_transaction_id:
        new_partner = _copy(transaction.linked_transaction)
        new_partner.linked_transaction = new_transaction
        new_partner.save()
        new_transaction.linked_transaction = new_partner
        new_transaction.save()
    return new_transaction


@only_htmx
@login_required
def bulk_pay_transactions(request):
    transactions = _selected(Transaction.objects, request)
    count = transactions.count()
    transactions.update(is_paid=True)

    messages.success(
        request,
        ngettext_lazy(
            "%(count)s transaction marked as paid",
            "%(count)s transactions marked as paid",
            count,
        )
        % {"count": count},
    )

    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "updated, paid"},
    )


@only_htmx
@login_required
def bulk_unpay_transactions(request):
    transactions = _selected(Transaction.objects, request)
    count = transactions.count()
    transactions.update(is_paid=False)

    messages.success(
        request,
        ngettext_lazy(
            "%(count)s transaction marked as not paid",
            "%(count)s transactions marked as not paid",
            count,
        )
        % {"count": count},
    )

    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "updated, unpaid"},
    )


@only_htmx
@login_required
def bulk_delete_transactions(request):
    transactions = _selected(Transaction.objects, request)
    deleted_ids = [str(pk) for pk in transactions.values_list("id", flat=True)]
    count = len(deleted_ids)
    transactions.delete()

    messages.success(
        request,
        ngettext_lazy(
            "%(count)s transaction deleted successfully",
            "%(count)s transactions deleted successfully",
            count,
        )
        % {"count": count},
    )

    # The list isn't reloaded, the client removes the rows it already has and
    # drops any divider left empty.
    # See templates/includes/scripts/hyperscript/transactions.html
    return HttpResponse(
        status=204,
        headers={
            "HX-Trigger": json.dumps(
                {
                    "transactions_deleted": {"ids": deleted_ids},
                    "selective_update": None,
                    "toasts": None,
                }
            )
        },
    )


@only_htmx
@login_required
def bulk_undelete_transactions(request):
    transactions = _selected(Transaction.deleted_objects, request)
    count = transactions.count()
    transactions.update(deleted=False, deleted_at=None, emit_signal=False)

    messages.success(
        request,
        ngettext_lazy(
            "%(count)s transaction restored successfully",
            "%(count)s transactions restored successfully",
            count,
        )
        % {"count": count},
    )

    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "updated"},
    )


@only_htmx
@login_required
def bulk_clone_transactions(request):
    selected_transactions = request.GET.getlist("transactions", [])
    transactions = Transaction.objects.filter(id__in=selected_transactions)
    count = transactions.count()

    cloned_ids = set()
    for transaction in transactions:
        # Both sides of a transfer selected: clone the pair once
        if transaction.linked_transaction_id in cloned_ids:
            continue
        clone_transaction(transaction)
        cloned_ids.add(transaction.id)

    messages.success(
        request,
        ngettext_lazy(
            "%(count)s transaction duplicated successfully",
            "%(count)s transactions duplicated successfully",
            count,
        )
        % {"count": count},
    )

    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "updated"},
    )
