from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.accounts.forms import AccountGroupForm
from apps.accounts.models import AccountGroup
from apps.common.decorators.htmx import only_htmx


@login_required
@require_http_methods(["GET"])
def account_groups_index(request):
    return render(
        request,
        "account_groups/pages/index.html",
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def account_groups_list(request):
    account_groups = AccountGroup.objects.all().order_by("id")
    return render(
        request,
        "account_groups/fragments/list.html",
        {"account_groups": account_groups},
    )


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def account_group_add(request, **kwargs):
    if request.method == "POST":
        form = AccountGroupForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("Account Group added successfully"))

            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": "updated, hide_offcanvas, toasts",
                },
            )
    else:
        form = AccountGroupForm()

    return render(
        request,
        "account_groups/fragments/add.html",
        {"form": form},
    )


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def account_group_edit(request, pk):
    account_group = get_object_or_404(AccountGroup, id=pk)

    if request.method == "POST":
        form = AccountGroupForm(request.POST, instance=account_group)
        if form.is_valid():
            form.save()
            messages.success(request, _("Account Group updated successfully"))

            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": "updated, hide_offcanvas, toasts",
                },
            )
    else:
        form = AccountGroupForm(instance=account_group)

    return render(
        request,
        "account_groups/fragments/edit.html",
        {"form": form, "account_group": account_group},
    )


@only_htmx
@login_required
@csrf_exempt
@require_http_methods(["DELETE"])
def account_group_delete(request, pk):
    account_group = get_object_or_404(AccountGroup, id=pk)

    account_group.delete()

    messages.success(request, _("Account Group deleted successfully"))

    return HttpResponse(
        status=204,
        headers={
            "HX-Trigger": "updated, hide_offcanvas, toasts",
        },
    )
