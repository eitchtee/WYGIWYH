# apps/dca_tracker/views.py
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.db.models import Sum, Avg
from django.db.models.functions import TruncMonth

from .models import DCAStrategy, DCAEntry
from .forms import DCAStrategyForm, DCAEntryForm


@login_required
def strategy_list(request):
    strategies = DCAStrategy.objects.all()
    return render(request, "dca/strategy_list.html", {"strategies": strategies})


from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.db.models import Sum, Avg
from django.db.models.functions import TruncMonth


@login_required
def strategy_detail(request, pk):
    strategy = get_object_or_404(DCAStrategy, id=pk)
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
    }
    return render(request, "dca/strategy_detail.html", context)
