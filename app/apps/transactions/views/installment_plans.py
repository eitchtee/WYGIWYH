from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.common.decorators.htmx import only_htmx
from apps.transactions.forms import InstallmentPlanForm
from apps.transactions.models import InstallmentPlan


@login_required
@require_http_methods(["GET"])
def installment_plans_index(request):
    return render(
        request,
        "installment_plans/pages/index.html",
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def installment_plans_list(request):
    installment_plans = InstallmentPlan.objects.all().order_by("-end_date")

    return render(
        request,
        "installment_plans/fragments/list.html",
        {"installment_plans": installment_plans},
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def installment_plan_transactions(request, installment_plan_id):
    installment_plan = get_object_or_404(InstallmentPlan, id=installment_plan_id)
    transactions = installment_plan.transactions.all().order_by("reference_date", "id")
    print(transactions)

    return render(
        request,
        "installment_plans/fragments/list_transactions.html",
        {"installment_plan": installment_plan, "transactions": transactions},
    )


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def installment_plan_add(request):
    if request.method == "POST":
        form = InstallmentPlanForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("Installment Plan added successfully"))

            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": "updated, hide_offcanvas, toasts",
                },
            )
    else:
        form = InstallmentPlanForm()

    return render(
        request,
        "installment_plans/fragments/add.html",
        {"form": form},
    )


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def installment_plan_edit(request, installment_plan_id):
    installment_plan = get_object_or_404(InstallmentPlan, id=installment_plan_id)

    if request.method == "POST":
        form = InstallmentPlanForm(request.POST, instance=installment_plan)
        if form.is_valid():
            form.save()
            messages.success(request, _("Installment Plan updated successfully"))

            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": "updated, hide_offcanvas, toasts",
                },
            )
    else:
        form = InstallmentPlanForm(instance=installment_plan)

    return render(
        request,
        "installment_plans/fragments/edit.html",
        {"form": form, "installment_plan": installment_plan},
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def installment_plan_refresh(request, installment_plan_id):
    installment_plan = get_object_or_404(InstallmentPlan, id=installment_plan_id)
    installment_plan.update_transactions()

    messages.success(request, _("Installment Plan refreshed successfully"))

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
def installment_plan_delete(request, installment_plan_id):
    installment_plan = get_object_or_404(InstallmentPlan, id=installment_plan_id)

    installment_plan.delete()

    messages.success(request, _("Installment Plan deleted successfully"))

    return HttpResponse(
        status=204,
        headers={
            "HX-Trigger": "updated, hide_offcanvas, toasts",
        },
    )
