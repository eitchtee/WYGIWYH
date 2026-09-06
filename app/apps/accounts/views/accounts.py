from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from apps.accounts.forms import AccountForm
from apps.accounts.models import Account
from apps.common.decorators.htmx import only_htmx
from apps.common.functions.permissions import (
    EDIT,
    READ,
    get_shared_object_or_error,
)
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
    accounts = Account.objects.all().order_by("name")
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
    account = get_shared_object_or_error(Account, request, id=pk, level=EDIT)

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
    obj = get_shared_object_or_error(Account, request, id=pk, level=EDIT)

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
    account = get_shared_object_or_error(Account, request, id=pk, level=READ)

    if account.is_editable_by(request.user):
        account.delete()
        messages.success(request, _("Account deleted successfully"))
    elif account.shared_with.filter(pk=request.user.pk).exists():
        # Someone else's object shared with us: we can drop our own access
        # to it, but never delete it.
        account.shared_with.remove(request.user)
        messages.success(request, _("Item no longer shared with you"))
    else:
        raise PermissionDenied

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
    # Only flips the calling user's own row in untracked_by, so visibility --
    # not ownership -- is the right bar here.
    account = get_shared_object_or_error(Account, request, id=pk, level=READ)
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
    account = get_shared_object_or_error(Account, request, id=pk, level=EDIT)

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
