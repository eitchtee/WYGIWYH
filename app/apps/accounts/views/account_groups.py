from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from apps.accounts.forms import AccountGroupForm
from apps.accounts.models import AccountGroup
from apps.common.decorators.htmx import only_htmx
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
    account_group = get_object_or_404(AccountGroup, id=pk)

    if account_group.owner and account_group.owner != request.user:
        messages.error(request, _("Only the owner can edit this"))

        return HttpResponse(
            status=204,
            headers={
                "HX-Trigger": "updated, hide_offcanvas",
            },
        )

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
    account_group = get_object_or_404(AccountGroup, id=pk)

    if (
        account_group.owner != request.user
        and request.user in account_group.shared_with.all()
    ):
        account_group.shared_with.remove(request.user)
        messages.success(request, _("Item no longer shared with you"))
    else:
        account_group.delete()
        messages.success(request, _("Account Group deleted successfully"))

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
    account_group = get_object_or_404(AccountGroup, id=pk)

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
def account_share(request, pk):
    obj = get_object_or_404(AccountGroup, id=pk)

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
