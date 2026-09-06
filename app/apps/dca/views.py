from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Sum, Avg
from django.db.models.functions import TruncMonth
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
from apps.dca.forms import DCAEntryForm, DCAStrategyForm
from apps.dca.models import DCAStrategy, DCAEntry
from apps.common.models import SharedObject
from apps.common.forms import SharedObjectForm


@login_required
def strategy_index(request):
    return render(request, "dca/pages/strategy_index.html")


@only_htmx
@login_required
def strategy_list(request):
    strategies = DCAStrategy.objects.all().order_by("name")
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
                    "HX-Trigger": "updated, hide_offcanvas",
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
    dca_strategy = get_shared_object_or_error(
        DCAStrategy, request, id=strategy_id, level=EDIT
    )

    if request.method == "POST":
        form = DCAStrategyForm(request.POST, instance=dca_strategy)
        if form.is_valid():
            form.save()
            messages.success(request, _("DCA Strategy updated successfully"))

            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": "updated, hide_offcanvas",
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
@require_http_methods(["DELETE"])
def strategy_delete(request, strategy_id):
    dca_strategy = get_shared_object_or_error(
        DCAStrategy, request, id=strategy_id, level=READ
    )

    if dca_strategy.is_editable_by(request.user):
        dca_strategy.delete()
        messages.success(request, _("DCA strategy deleted successfully"))
    elif dca_strategy.shared_with.filter(pk=request.user.pk).exists():
        # Someone else's object shared with us: we can drop our own access
        # to it, but never delete it.
        dca_strategy.shared_with.remove(request.user)
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
def strategy_take_ownership(request, strategy_id):
    dca_strategy = get_shared_object_or_error(
        DCAStrategy, request, id=strategy_id, level=EDIT
    )

    if not dca_strategy.owner:
        dca_strategy.owner = request.user
        dca_strategy.visibility = SharedObject.Visibility.private
        dca_strategy.save()

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
def strategy_share(request, pk):
    obj = get_shared_object_or_error(DCAStrategy, request, id=pk, level=EDIT)

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
        "dca/fragments/strategy/share.html",
        {"form": form, "object": obj},
    )


@login_required
def strategy_detail_index(request, strategy_id):
    strategy = get_shared_object_or_error(
        DCAStrategy, request, id=strategy_id, level=READ
    )

    return render(
        request,
        "dca/pages/strategy_detail_index.html",
        context={"strategy": strategy},
    )


@only_htmx
@login_required
def strategy_detail(request, strategy_id):
    strategy = get_shared_object_or_error(
        DCAStrategy, request, id=strategy_id, level=READ
    )
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
        "investment_frequency": strategy.investment_frequency_data(),
        "price_comparison_data": strategy.price_comparison_data(),
    }

    return render(request, "dca/fragments/strategy/details.html", context)


@only_htmx
@login_required
def strategy_entry_add(request, strategy_id):
    strategy = get_shared_object_or_error(
        DCAStrategy, request, id=strategy_id, level=EDIT
    )
    if request.method == "POST":
        form = DCAEntryForm(request.POST, strategy=strategy)
        if form.is_valid():
            form.save()
            messages.success(request, _("Entry added successfully"))

            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": "updated, hide_offcanvas",
                },
            )
    else:
        form = DCAEntryForm(strategy=strategy)

    return render(
        request,
        "dca/fragments/entry/add.html",
        {"form": form, "strategy": strategy},
    )


@only_htmx
@login_required
def strategy_entry_edit(request, strategy_id, entry_id):
    dca_entry = get_shared_object_or_error(
        DCAEntry,
        request,
        id=entry_id,
        strategy__id=strategy_id,
        level=EDIT,
        via="strategy",
    )

    if request.method == "POST":
        form = DCAEntryForm(request.POST, instance=dca_entry)
        if form.is_valid():
            form.save()
            messages.success(request, _("Entry updated successfully"))

            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": "updated, hide_offcanvas",
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
@require_http_methods(["DELETE"])
def strategy_entry_delete(request, entry_id, strategy_id):
    dca_entry = get_shared_object_or_error(
        DCAEntry,
        request,
        id=entry_id,
        strategy__id=strategy_id,
        level=EDIT,
        via="strategy",
    )

    dca_entry.delete()

    messages.success(request, _("Entry deleted successfully"))

    return HttpResponse(
        status=204,
        headers={
            "HX-Trigger": "updated, hide_offcanvas",
        },
    )
