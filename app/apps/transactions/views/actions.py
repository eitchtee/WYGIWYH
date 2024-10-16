from django.contrib.auth.decorators import login_required
from django.http import HttpResponse

from apps.common.decorators.htmx import only_htmx
from apps.transactions.models import Transaction


@only_htmx
@login_required
def bulk_pay_transactions(request):
    selected_transactions = request.GET.getlist("transactions", [])
    Transaction.objects.filter(id__in=selected_transactions).update(is_paid=True)

    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "updated, toast, paid"},
    )


@only_htmx
@login_required
def bulk_unpay_transactions(request):
    selected_transactions = request.GET.getlist("transactions", [])
    Transaction.objects.filter(id__in=selected_transactions).update(is_paid=False)

    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "updated, toast, unpaid"},
    )


@only_htmx
@login_required
def bulk_delete_transactions(request):
    selected_transactions = request.GET.getlist("transactions", [])
    Transaction.objects.filter(id__in=selected_transactions).delete()

    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "updated, toast"},
    )
