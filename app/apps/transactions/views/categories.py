from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.common.decorators.htmx import only_htmx
from apps.transactions.forms import TransactionCategoryForm
from apps.transactions.models import TransactionCategory


@login_required
@require_http_methods(["GET"])
def categories_list(request):
    categories = TransactionCategory.objects.all().order_by("id")
    return render(request, "categories/pages/list.html", {"categories": categories})


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def category_add(request, **kwargs):
    if request.method == "POST":
        form = TransactionCategoryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("Category added successfully"))

            return HttpResponse(
                status=204,
                headers={
                    "HX-Location": reverse("categories_list"),
                    "HX-Trigger": "hide_offcanvas, toasts",
                },
            )
    else:
        form = TransactionCategoryForm()

    return render(
        request,
        "categories/fragments/add.html",
        {"form": form},
    )


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def category_edit(request, category_id):
    category = get_object_or_404(TransactionCategory, id=category_id)

    if request.method == "POST":
        form = TransactionCategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, _("Category updated successfully"))

            return HttpResponse(
                status=204,
                headers={
                    "HX-Location": reverse("categories_list"),
                    "HX-Trigger": "hide_offcanvas, toasts",
                },
            )
    else:
        form = TransactionCategoryForm(instance=category)

    return render(
        request,
        "categories/fragments/edit.html",
        {"form": form, "category": category},
    )


@only_htmx
@login_required
@csrf_exempt
@require_http_methods(["DELETE"])
def category_delete(request, category_id):
    category = get_object_or_404(TransactionCategory, id=category_id)

    category.delete()

    messages.success(request, _("Category deleted successfully"))

    return HttpResponse(
        status=204,
        headers={"HX-Location": reverse("categories_list")},
    )
