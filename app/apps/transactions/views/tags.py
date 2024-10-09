from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.common.decorators.htmx import only_htmx
from apps.transactions.forms import TransactionTagForm
from apps.transactions.models import TransactionTag


@login_required
@require_http_methods(["GET"])
def tag_list(request):
    tags = TransactionTag.objects.all().order_by("id")
    return render(request, "tags/pages/list.html", {"tags": tags})


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
                    "HX-Location": reverse("tags_list"),
                    "HX-Trigger": "hide_offcanvas, toasts",
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

    if request.method == "POST":
        form = TransactionTagForm(request.POST, instance=tag)
        if form.is_valid():
            form.save()
            messages.success(request, _("Tag updated successfully"))

            return HttpResponse(
                status=204,
                headers={
                    "HX-Location": reverse("tags_list"),
                    "HX-Trigger": "hide_offcanvas, toasts",
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
@csrf_exempt
@require_http_methods(["DELETE"])
def tag_delete(request, tag_id):
    tag = get_object_or_404(TransactionTag, id=tag_id)

    tag.delete()

    messages.success(request, _("Tag deleted successfully"))

    return HttpResponse(
        status=204,
        headers={"HX-Location": reverse("tags_list")},
    )
