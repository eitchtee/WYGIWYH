from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.common.decorators.htmx import only_htmx
from apps.currencies.forms import CurrencyForm
from apps.currencies.models import Currency


@login_required
@require_http_methods(["GET"])
def currencies_index(request):
    return render(
        request,
        "currencies/pages/index.html",
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def currencies_list(request):
    currencies = Currency.objects.all().order_by("id")
    return render(
        request,
        "currencies/fragments/list.html",
        {"currencies": currencies},
    )


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def currency_add(request, **kwargs):
    if request.method == "POST":
        form = CurrencyForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("Currency added successfully"))

            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": "updated, hide_offcanvas, toasts",
                },
            )
    else:
        form = CurrencyForm()

    return render(
        request,
        "currencies/fragments/add.html",
        {"form": form},
    )


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def currency_edit(request, pk):
    currency = get_object_or_404(Currency, id=pk)

    if request.method == "POST":
        form = CurrencyForm(request.POST, instance=currency)
        if form.is_valid():
            form.save()
            messages.success(request, _("Currency updated successfully"))

            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": "updated, hide_offcanvas, toasts",
                },
            )
    else:
        form = CurrencyForm(instance=currency)

    return render(
        request,
        "currencies/fragments/edit.html",
        {"form": form, "currency": currency},
    )


@only_htmx
@login_required
@csrf_exempt
@require_http_methods(["DELETE"])
def currency_delete(request, pk):
    currency = get_object_or_404(Currency, id=pk)

    currency.delete()

    messages.success(request, _("Currency deleted successfully"))

    return HttpResponse(
        status=204,
        headers={
            "HX-Trigger": "updated, hide_offcanvas, toasts",
        },
    )
