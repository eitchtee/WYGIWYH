from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from apps.accounts.forms import AccountGroupForm
from apps.accounts.models import AccountGroup
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
def account_groups_index(request):
    return render(
        request,
        "account_groups/pages/index.html",
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def account_groups_list(request):
    account_groups = AccountGroup.objects.all().order_by("name")
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
                    "HX-Trigger": "updated, hide_offcanvas",
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
    account_group = get_shared_object_or_error(AccountGroup, request, id=pk, level=EDIT)

    if request.method == "POST":
        form = AccountGroupForm(request.POST, instance=account_group)
        if form.is_valid():
            form.save()
            messages.success(request, _("Account Group updated successfully"))

            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": "updated, hide_offcanvas",
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
@require_http_methods(["DELETE"])
def account_group_delete(request, pk):
    account_group = get_shared_object_or_error(AccountGroup, request, id=pk, level=READ)

    if account_group.is_editable_by(request.user):
        account_group.delete()
        messages.success(request, _("Account Group deleted successfully"))
    elif account_group.shared_with.filter(pk=request.user.pk).exists():
        # Someone else's object shared with us: we can drop our own access
        # to it, but never delete it.
        account_group.shared_with.remove(request.user)
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
def account_group_take_ownership(request, pk):
    account_group = get_shared_object_or_error(AccountGroup, request, id=pk, level=EDIT)

    if not account_group.owner:
        account_group.owner = request.user
        account_group.visibility = SharedObject.Visibility.private
        account_group.save()

        messages.success(request, _("Ownership taken successfully"))

    return HttpResponse(
        status=204,
        headers={
            "HX-Trigger": "updated, hide_offcanvas",
        },
    )


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def account_group_share(request, pk):
    obj = get_shared_object_or_error(AccountGroup, request, id=pk, level=EDIT)

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
