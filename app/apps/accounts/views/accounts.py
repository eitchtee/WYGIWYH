from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from apps.accounts.forms import AccountForm
from apps.accounts.models import Account
from apps.common.decorators.htmx import only_htmx


@login_required
@require_http_methods(["GET"])
def accounts_index(request):
    return render(
        request,
        "accounts/pages/index.html",
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def accounts_list(request):
    accounts = Account.objects.all().order_by("id")
    return render(
        request,
        "accounts/fragments/list.html",
        {"accounts": accounts},
    )


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def account_add(request, **kwargs):
    if request.method == "POST":
        form = AccountForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("Account added successfully"))

            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": "updated, hide_offcanvas",
                },
            )
    else:
        form = AccountForm()

    return render(
        request,
        "accounts/fragments/add.html",
        {"form": form},
    )


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def account_edit(request, pk):
    account = get_object_or_404(Account, id=pk)

    if request.method == "POST":
        form = AccountForm(request.POST, instance=account)
        if form.is_valid():
            form.save()
            messages.success(request, _("Account updated successfully"))

            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": "updated, hide_offcanvas",
                },
            )
    else:
        form = AccountForm(instance=account)

    return render(
        request,
        "accounts/fragments/edit.html",
        {"form": form, "account": account},
    )


@only_htmx
@login_required
@require_http_methods(["DELETE"])
def account_delete(request, pk):
    account = get_object_or_404(Account, id=pk)

    account.delete()

    messages.success(request, _("Account deleted successfully"))

    return HttpResponse(
        status=204,
        headers={
            "HX-Trigger": "updated, hide_offcanvas",
        },
    )
