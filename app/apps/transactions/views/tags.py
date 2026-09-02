from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from apps.common.decorators.htmx import only_htmx
from apps.common.functions.permissions import (
    EDIT,
    READ,
    get_shared_object_or_error,
)
from apps.transactions.forms import TransactionTagForm
from apps.transactions.models import TransactionTag
from apps.common.models import SharedObject
from apps.common.forms import SharedObjectForm


@login_required
@require_http_methods(["GET"])
def tags_index(request):
    return render(
        request,
        "tags/pages/index.html",
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def tags_list(request):
    return render(
        request,
        "tags/fragments/list.html",
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def tags_table_active(request):
    tags = TransactionTag.objects.filter(active=True).order_by("name")
    return render(
        request,
        "tags/fragments/table.html",
        {"tags": tags, "active": True},
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def tags_table_archived(request):
    tags = TransactionTag.objects.filter(active=False).order_by("name")
    return render(
        request,
        "tags/fragments/table.html",
        {"tags": tags, "active": False},
    )


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def tag_add(request, **kwargs):
    if request.method == "POST":
        form = TransactionTagForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("Tag added successfully"))

            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": "updated, hide_offcanvas",
                },
            )
    else:
        form = TransactionTagForm()

    return render(
        request,
        "tags/fragments/add.html",
        {"form": form},
    )


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def tag_edit(request, tag_id):
    tag = get_shared_object_or_error(TransactionTag, request, id=tag_id, level=EDIT)

    if request.method == "POST":
        form = TransactionTagForm(request.POST, instance=tag)
        if form.is_valid():
            form.save()
            messages.success(request, _("Tag updated successfully"))

            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": "updated, hide_offcanvas",
                },
            )
    else:
        form = TransactionTagForm(instance=tag)

    return render(
        request,
        "tags/fragments/edit.html",
        {"form": form, "tag": tag},
    )


@only_htmx
@login_required
@require_http_methods(["DELETE"])
def tag_delete(request, tag_id):
    tag = get_shared_object_or_error(TransactionTag, request, id=tag_id, level=READ)

    if tag.is_editable_by(request.user):
        tag.delete()
        messages.success(request, _("Tag deleted successfully"))
    elif tag.shared_with.filter(pk=request.user.pk).exists():
        # Someone else's object shared with us: we can drop our own access
        # to it, but never delete it.
        tag.shared_with.remove(request.user)
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
def tag_take_ownership(request, tag_id):
    tag = get_shared_object_or_error(TransactionTag, request, id=tag_id, level=EDIT)

    if not tag.owner:
        tag.owner = request.user
        tag.visibility = SharedObject.Visibility.private
        tag.save()

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
def tag_share(request, pk):
    obj = get_shared_object_or_error(TransactionTag, request, id=pk, level=EDIT)

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
        "tags/fragments/share.html",
        {"form": form, "object": obj},
    )
