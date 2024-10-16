from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.common.decorators.htmx import only_htmx
from apps.currencies.forms import ExchangeRateForm
from apps.currencies.models import ExchangeRate


@login_required
@require_http_methods(["GET"])
def exchange_rates_index(request):
    return render(
        request,
        "exchange_rates/pages/index.html",
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def exchange_rates_list(request):
    exchange_rates = ExchangeRate.objects.all().order_by("-date")
    return render(
        request,
        "exchange_rates/fragments/list.html",
        {"exchange_rates": exchange_rates},
    )


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def exchange_rate_add(request):
    if request.method == "POST":
        form = ExchangeRateForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("Exchange rate added successfully"))

            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": "updated, hide_offcanvas, toasts",
                },
            )
    else:
        form = ExchangeRateForm()

    return render(
        request,
        "exchange_rates/fragments/add.html",
        {"form": form},
    )


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def exchange_rate_edit(request, pk):
    exchange_rate = get_object_or_404(ExchangeRate, id=pk)

    if request.method == "POST":
        form = ExchangeRateForm(request.POST, instance=exchange_rate)
        if form.is_valid():
            form.save()
            messages.success(request, _("Exchange rate updated successfully"))

            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": "updated, hide_offcanvas, toasts",
                },
            )
    else:
        form = ExchangeRateForm(instance=exchange_rate)

    return render(
        request,
        "exchange_rates/fragments/edit.html",
        {"form": form, "exchange_rate": exchange_rate},
    )


@only_htmx
@login_required
@csrf_exempt
@require_http_methods(["DELETE"])
def exchange_rate_delete(request, pk):
    exchange_rate = get_object_or_404(ExchangeRate, id=pk)

    exchange_rate.delete()

    messages.success(request, _("Exchange rate deleted successfully"))

    return HttpResponse(
        status=204,
        headers={
            "HX-Trigger": "updated, hide_offcanvas, toasts",
        },
    )
