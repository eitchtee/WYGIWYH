import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from apps.bank_sync.forms import BankSyncAccountFormSet, BankSyncServiceForm
from apps.bank_sync.models import BankSyncService
from apps.bank_sync.sync import refresh_remote_accounts
from apps.bank_sync.tasks import manual_bank_sync
from apps.common.decorators.demo import disabled_on_demo
from apps.common.decorators.htmx import only_htmx

logger = logging.getLogger(__name__)

_CLOSE = {"HX-Trigger": "updated, hide_offcanvas"}


@login_required
@disabled_on_demo
@require_http_methods(["GET"])
def bank_sync_index(request):
    return render(request, "bank_sync/pages/index.html")


@only_htmx
@login_required
@disabled_on_demo
@require_http_methods(["GET"])
def bank_sync_list(request):
    services = BankSyncService.objects.prefetch_related("accounts")
    return render(request, "bank_sync/fragments/list.html", {"services": services})


def _service_form(request, instance=None):
    url = request.path
    if request.method == "POST":
        return BankSyncServiceForm(request.POST, instance=instance, refresh_url=url)
    # A GET with params comes from switching provider: keep what was typed
    return BankSyncServiceForm(
        instance=instance, initial=request.GET.dict() or None, refresh_url=url
    )


@only_htmx
@login_required
@disabled_on_demo
@require_http_methods(["GET", "POST"])
def bank_sync_add(request):
    form = _service_form(request)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Service added successfully"))
        return HttpResponse(status=204, headers=_CLOSE)

    return render(
        request,
        "bank_sync/fragments/form.html",
        {"form": form, "title": _("Add bank sync service")},
    )


@only_htmx
@login_required
@disabled_on_demo
@require_http_methods(["GET", "POST"])
def bank_sync_edit(request, pk):
    service = get_object_or_404(BankSyncService, id=pk)
    form = _service_form(request, instance=service)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Service updated successfully"))
        return HttpResponse(status=204, headers=_CLOSE)

    return render(
        request,
        "bank_sync/fragments/form.html",
        {"form": form, "title": _("Edit bank sync service")},
    )


@only_htmx
@login_required
@disabled_on_demo
@require_http_methods(["DELETE"])
def bank_sync_delete(request, pk):
    get_object_or_404(BankSyncService, id=pk).delete()
    messages.success(request, _("Service deleted successfully"))
    return HttpResponse(status=204, headers=_CLOSE)


@only_htmx
@login_required
@disabled_on_demo
@require_http_methods(["GET", "POST"])
def bank_sync_accounts(request, pk):
    service = get_object_or_404(BankSyncService, id=pk)
    error = None

    if request.method == "POST":
        formset = BankSyncAccountFormSet(request.POST, queryset=service.accounts.all())
        if formset.is_valid():
            formset.save()
            messages.success(request, _("Accounts updated successfully"))
            return HttpResponse(status=204, headers=_CLOSE)
    else:
        try:
            refresh_remote_accounts(service)
        except Exception as e:
            logger.warning(f"Could not list accounts for {service.name}: {e}")
            error = _("Couldn't load the accounts from the provider: %(error)s") % {
                "error": e
            }
        formset = BankSyncAccountFormSet(queryset=service.accounts.all())

    return render(
        request,
        "bank_sync/fragments/accounts.html",
        {"service": service, "formset": formset, "error": error},
    )


@only_htmx
@login_required
@disabled_on_demo
@require_http_methods(["GET"])
def bank_sync_sync_now(request, pk):
    service = get_object_or_404(BankSyncService, id=pk)
    manual_bank_sync.defer(service_id=service.id)
    messages.success(request, _("Sync queued successfully"))
    return HttpResponse(status=204, headers={"HX-Trigger": "toasts"})
