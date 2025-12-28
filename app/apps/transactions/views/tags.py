from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from apps.common.decorators.htmx import only_htmx
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
    tag = get_object_or_404(TransactionTag, id=tag_id)

    if tag.owner and tag.owner != request.user:
        messages.error(request, _("Only the owner can edit this"))

        return HttpResponse(
            status=204,
            headers={
                "HX-Trigger": "updated, hide_offcanvas",
            },
        )

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
    tag = get_object_or_404(TransactionTag, id=tag_id)

    if tag.owner != request.user and request.user in tag.shared_with.all():
        tag.shared_with.remove(request.user)
        messages.success(request, _("Item no longer shared with you"))
    else:
        tag.delete()
        messages.success(request, _("Tag deleted successfully"))

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
    tag = get_object_or_404(TransactionTag, id=tag_id)

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
    obj = get_object_or_404(TransactionTag, id=pk)

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
        "tags/fragments/share.html",
        {"form": form, "object": obj},
    )
