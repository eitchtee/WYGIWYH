from copy import deepcopy

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.utils.translation import gettext_lazy as _, ngettext_lazy

from apps.common.decorators.htmx import only_htmx
from apps.transactions.models import Transaction
from apps.rules.signals import transaction_updated


@only_htmx
@login_required
def bulk_pay_transactions(request):
    selected_transactions = request.GET.getlist("transactions", [])
    transactions = Transaction.objects.filter(id__in=selected_transactions)
    count = transactions.count()
    transactions.update(is_paid=True)

    for transaction in transactions:
        transaction_updated.send(sender=transaction)

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
    selected_transactions = request.GET.getlist("transactions", [])
    transactions = Transaction.objects.filter(id__in=selected_transactions)
    count = transactions.count()
    transactions.update(is_paid=False)

    for transaction in transactions:
        transaction_updated.send(sender=transaction)

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
    selected_transactions = request.GET.getlist("transactions", [])
    transactions = Transaction.all_objects.filter(id__in=selected_transactions)
    count = transactions.count()
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

    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "updated"},
    )


@only_htmx
@login_required
def bulk_undelete_transactions(request):
    selected_transactions = request.GET.getlist("transactions", [])
    transactions = Transaction.deleted_objects.filter(id__in=selected_transactions)
    count = transactions.count()
    transactions.update(deleted=False, deleted_at=None)

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

    for transaction in transactions:
        new_transaction = deepcopy(transaction)
        new_transaction.pk = None
        new_transaction.installment_plan = None
        new_transaction.installment_id = None
        new_transaction.recurring_transaction = None
        new_transaction.internal_id = None
        new_transaction.save()

        new_transaction.tags.add(*transaction.tags.all())
        new_transaction.entities.add(*transaction.entities.all())

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
