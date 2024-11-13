# apps/dca_tracker/views.py
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Avg
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.common.decorators.htmx import only_htmx
from apps.dca.models import DCAStrategy, DCAEntry
from apps.dca.forms import DCAEntryForm, DCAStrategyForm


@login_required
def strategy_index(request):
    return render(request, "dca/pages/strategy_index.html")


@only_htmx
@login_required
def strategy_list(request):
    strategies = DCAStrategy.objects.all().order_by("created_at")
    return render(
        request, "dca/fragments/strategy/list.html", {"strategies": strategies}
    )


@only_htmx
@login_required
def strategy_add(request):
    if request.method == "POST":
        form = DCAStrategyForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("DCA Strategy added successfully"))

            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": "updated, hide_offcanvas, toasts",
                },
            )
    else:
        form = DCAStrategyForm()

    return render(
        request,
        "dca/fragments/strategy/add.html",
        {"form": form},
    )


@only_htmx
@login_required
def strategy_edit(request, strategy_id):
    dca_strategy = get_object_or_404(DCAStrategy, id=strategy_id)

    if request.method == "POST":
        form = DCAStrategyForm(request.POST, instance=dca_strategy)
        if form.is_valid():
            form.save()
            messages.success(request, _("DCA Strategy updated successfully"))

            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": "updated, hide_offcanvas, toasts",
                },
            )
    else:
        form = DCAStrategyForm(instance=dca_strategy)

    return render(
        request,
        "dca/fragments/strategy/edit.html",
        {"form": form, "strategy": dca_strategy},
    )


@only_htmx
@login_required
@csrf_exempt
@require_http_methods(["DELETE"])
def strategy_delete(request, strategy_id):
    dca_strategy = get_object_or_404(DCAStrategy, id=strategy_id)

    dca_strategy.delete()

    messages.success(request, _("DCA strategy deleted successfully"))

    return HttpResponse(
        status=204,
        headers={
            "HX-Trigger": "updated, hide_offcanvas, toasts",
        },
    )


@login_required
def strategy_detail_index(request, strategy_id):
    strategy = get_object_or_404(DCAStrategy, id=strategy_id)

    return render(
        request,
        "dca/pages/strategy_detail_index.html",
        context={"strategy": strategy},
    )


@only_htmx
@login_required
def strategy_detail(request, strategy_id):
    strategy = get_object_or_404(DCAStrategy, id=strategy_id)
    entries = strategy.entries.all()

    # Calculate monthly aggregates
    monthly_data = (
        entries.annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(
            total_paid=Sum("amount_paid"),
            total_received=Sum("amount_received"),
            avg_entry_price=Avg("amount_paid") / Avg("amount_received"),
        )
        .order_by("month")
    )

    # Prepare entries data with current values
    entries_data = [
        {
            "entry": entry,
            "current_value": entry.current_value(),
            "profit_loss": entry.profit_loss(),
            "profit_loss_percentage": entry.profit_loss_percentage(),
        }
        for entry in entries
    ]
    entries_data.reverse()

    context = {
        "strategy": strategy,
        "entries": entries,
        "entries_data": entries_data,
        "monthly_data": monthly_data,
        "total_invested": strategy.total_invested(),
        "total_received": strategy.total_received(),
        "average_entry_price": strategy.average_entry_price(),
        "total_entries": strategy.total_entries(),
        "current_total_value": strategy.current_total_value(),
        "total_profit_loss": strategy.total_profit_loss(),
        "total_profit_loss_percentage": strategy.total_profit_loss_percentage(),
        "investment_frequency": strategy.investment_frequency_data(),
        "price_comparison_data": strategy.price_comparison_data(),
    }

    return render(request, "dca/fragments/strategy/details.html", context)


@only_htmx
@login_required
def strategy_entry_add(request, strategy_id):
    strategy = get_object_or_404(DCAStrategy, id=strategy_id)
    if request.method == "POST":
        form = DCAEntryForm(request.POST)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.strategy = strategy
            entry.save()
            messages.success(request, _("Entry added successfully"))

            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": "updated, hide_offcanvas, toasts",
                },
            )
    else:
        form = DCAEntryForm()

    return render(
        request,
        "dca/fragments/entry/add.html",
        {"form": form, "strategy": strategy},
    )


@only_htmx
@login_required
def strategy_entry_edit(request, strategy_id, entry_id):
    dca_entry = get_object_or_404(DCAEntry, id=entry_id, strategy__id=strategy_id)

    if request.method == "POST":
        form = DCAEntryForm(request.POST, instance=dca_entry)
        if form.is_valid():
            form.save()
            messages.success(request, _("Entry updated successfully"))

            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": "updated, hide_offcanvas, toasts",
                },
            )
    else:
        form = DCAEntryForm(instance=dca_entry)

    return render(
        request,
        "dca/fragments/entry/edit.html",
        {"form": form, "dca_entry": dca_entry},
    )


@only_htmx
@login_required
@csrf_exempt
@require_http_methods(["DELETE"])
def strategy_entry_delete(request, entry_id, strategy_id):
    dca_entry = get_object_or_404(DCAEntry, id=entry_id, strategy__id=strategy_id)

    dca_entry.delete()

    messages.success(request, _("Entry deleted successfully"))

    return HttpResponse(
        status=204,
        headers={
            "HX-Trigger": "updated, hide_offcanvas, toasts",
        },
    )
