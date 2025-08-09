from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from apps.accounts.forms import AccountForm
from apps.accounts.models import Account
from apps.common.decorators.htmx import only_htmx
from apps.common.models import SharedObject
from apps.common.forms import SharedObjectForm


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
    if account.owner and account.owner != request.user:
        messages.error(request, _("Only the owner can edit this"))

        return HttpResponse(
            status=204,
            headers={
                "HX-Trigger": "updated, hide_offcanvas",
            },
        )

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
@require_http_methods(["GET", "POST"])
def account_share(request, pk):
    obj = get_object_or_404(Account, id=pk)

    if obj.owner and obj.owner != request.user:
        messages.error(request, _("Only the owner can edit this"))

        return HttpResponse(
            status=204,
            headers={
                "HX-Trigger": "updated, hide_offcanvas",
            },
        )

    if request.method == "POST":
        form = SharedObjectForm(request.POST, instance=obj, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, _("Configuration saved successfully"))

            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": "updated, hide_offcanvas",
                },
            )
    else:
        form = SharedObjectForm(instance=obj, user=request.user)

    return render(
        request,
        "accounts/fragments/share.html",
        {"form": form, "object": obj},
    )


@only_htmx
@login_required
@require_http_methods(["DELETE"])
def account_delete(request, pk):
    account = get_object_or_404(Account, id=pk)

    if account.owner != request.user and request.user in account.shared_with.all():
        account.shared_with.remove(request.user)
        messages.success(request, _("Item no longer shared with you"))
    else:
        account.delete()
        messages.success(request, _("Account deleted successfully"))

    return HttpResponse(
        status=204,
        headers={
            "HX-Trigger": "updated, hide_offcanvas",
        },
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def account_toggle_untracked(request, pk):
    account = get_object_or_404(Account, id=pk)
    if account.is_untracked_by():
        account.untracked_by.remove(request.user)
        messages.success(request, _("Account is now tracked"))
    else:
        account.untracked_by.add(request.user)
        messages.success(request, _("Account is now untracked"))

    return HttpResponse(
        status=204,
        headers={
            "HX-Trigger": "updated",
        },
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def account_take_ownership(request, pk):
    account = get_object_or_404(Account, id=pk)

    if not account.owner:
        account.owner = request.user
        account.visibility = SharedObject.Visibility.private
        account.save()

        messages.success(request, _("Ownership taken successfully"))

    return HttpResponse(
        status=204,
        headers={
            "HX-Trigger": "updated, hide_offcanvas",
        },
    )
