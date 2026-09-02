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
from apps.transactions.forms import TransactionEntityForm
from apps.transactions.models import TransactionEntity
from apps.common.models import SharedObject
from apps.common.forms import SharedObjectForm


@login_required
@require_http_methods(["GET"])
def entities_index(request):
    return render(
        request,
        "entities/pages/index.html",
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def entities_list(request):
    return render(
        request,
        "entities/fragments/list.html",
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def entities_table_active(request):
    entities = TransactionEntity.objects.filter(active=True).order_by("name")
    return render(
        request,
        "entities/fragments/table.html",
        {"entities": entities, "active": True},
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def entities_table_archived(request):
    entities = TransactionEntity.objects.filter(active=False).order_by("name")
    return render(
        request,
        "entities/fragments/table.html",
        {"entities": entities, "active": False},
    )


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def entity_add(request, **kwargs):
    if request.method == "POST":
        form = TransactionEntityForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("Entity added successfully"))

            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": "updated, hide_offcanvas",
                },
            )
    else:
        form = TransactionEntityForm()

    return render(
        request,
        "entities/fragments/add.html",
        {"form": form},
    )


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def entity_edit(request, entity_id):
    entity = get_shared_object_or_error(
        TransactionEntity, request, id=entity_id, level=EDIT
    )

    if request.method == "POST":
        form = TransactionEntityForm(request.POST, instance=entity)
        if form.is_valid():
            form.save()
            messages.success(request, _("Entity updated successfully"))

            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": "updated, hide_offcanvas",
                },
            )
    else:
        form = TransactionEntityForm(instance=entity)

    return render(
        request,
        "entities/fragments/edit.html",
        {"form": form, "entity": entity},
    )


@only_htmx
@login_required
@require_http_methods(["DELETE"])
def entity_delete(request, entity_id):
    entity = get_shared_object_or_error(
        TransactionEntity, request, id=entity_id, level=READ
    )

    if entity.is_editable_by(request.user):
        entity.delete()
        messages.success(request, _("Entity deleted successfully"))
    elif entity.shared_with.filter(pk=request.user.pk).exists():
        # Someone else's object shared with us: we can drop our own access
        # to it, but never delete it.
        entity.shared_with.remove(request.user)
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
def entity_take_ownership(request, entity_id):
    entity = get_shared_object_or_error(
        TransactionEntity, request, id=entity_id, level=EDIT
    )

    if not entity.owner:
        entity.owner = request.user
        entity.visibility = SharedObject.Visibility.private
        entity.save()

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
def entity_share(request, pk):
    obj = get_shared_object_or_error(TransactionEntity, request, id=pk, level=EDIT)

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
        "entities/fragments/share.html",
        {"form": form, "object": obj},
    )
