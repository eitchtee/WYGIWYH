from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import CharField, Value
from django.db.models.functions import Concat
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from apps.common.decorators.htmx import only_htmx
from apps.currencies.forms import ExchangeRateForm, ExchangeRateServiceForm
from apps.currencies.models import ExchangeRate, ExchangeRateService
from apps.currencies.tasks import manual_fetch_exchange_rates


@login_required
@require_http_methods(["GET"])
def exchange_rates_services_index(request):
    return render(
        request,
        "exchange_rates_services/pages/index.html",
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def exchange_rates_services_list(request):
    services = ExchangeRateService.objects.all()

    return render(
        request,
        "exchange_rates_services/fragments/list.html",
        {"services": services},
    )


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def exchange_rate_service_add(request):
    if request.method == "POST":
        form = ExchangeRateServiceForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("Service added successfully"))

            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": "updated, hide_offcanvas",
                },
            )
    else:
        form = ExchangeRateServiceForm()

    return render(
        request,
        "exchange_rates_services/fragments/add.html",
        {"form": form},
    )


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def exchange_rate_service_edit(request, pk):
    service = get_object_or_404(ExchangeRateService, id=pk)

    if request.method == "POST":
        form = ExchangeRateServiceForm(request.POST, instance=service)
        if form.is_valid():
            form.save()
            messages.success(request, _("Service updated successfully"))

            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": "updated, hide_offcanvas",
                },
            )
    else:
        form = ExchangeRateServiceForm(instance=service)

    return render(
        request,
        "exchange_rates_services/fragments/edit.html",
        {"form": form, "service": service},
    )


@only_htmx
@login_required
@require_http_methods(["DELETE"])
def exchange_rate_service_delete(request, pk):
    service = get_object_or_404(ExchangeRateService, id=pk)

    service.delete()

    messages.success(request, _("Service deleted successfully"))

    return HttpResponse(
        status=204,
        headers={
            "HX-Trigger": "updated, hide_offcanvas",
        },
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def exchange_rate_service_force_fetch(request):
    manual_fetch_exchange_rates.defer()
    messages.success(request, _("Services queued successfully"))

    return HttpResponse(
        status=204,
        headers={
            "HX-Trigger": "toasts",
        },
    )
