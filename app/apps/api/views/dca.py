from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.dca.models import DCAStrategy, DCAEntry
from apps.api.permissions import SHARED_OBJECT_PERMISSIONS
from apps.api.serializers import DCAStrategySerializer, DCAEntrySerializer


class DCAStrategyViewSet(viewsets.ModelViewSet):
    """Dollar-cost averaging plans: recurring buys of `target_currency` paid in
    `payment_currency`."""

    permission_classes = SHARED_OBJECT_PERMISSIONS
    queryset = DCAStrategy.objects.all()
    serializer_class = DCAStrategySerializer
    filterset_fields = {
        "name": ["exact", "icontains"],
        "target_currency": ["exact"],
        "payment_currency": ["exact"],
        "notes": ["exact", "icontains"],
        "created_at": ["exact", "gte", "lte", "gt", "lt"],
        "updated_at": ["exact", "gte", "lte", "gt", "lt"],
    }
    search_fields = ["name", "notes"]
    ordering_fields = "__all__"

    def get_queryset(self):
        return DCAStrategy.objects.all()

    @extend_schema(
        summary="Buys over time",
        description="Chart data for the strategy's buys: `labels` are entry dates in the server's display format.",
        responses=OpenApiTypes.OBJECT,
    )
    @action(detail=True, methods=["get"])
    def investment_frequency(self, request, pk=None):
        strategy = self.get_object()
        return Response(strategy.investment_frequency_data())

    @extend_schema(
        summary="Paid vs current value per entry",
        description=(
            "Chart data, one item per entry. Despite their names, `entry_prices` holds "
            "the amount paid and `current_prices` the entry's current value, both in the "
            "payment currency; `amounts_bought` is the amount received. `labels` are entry "
            "dates in the server's display format."
        ),
        responses=OpenApiTypes.OBJECT,
    )
    @action(detail=True, methods=["get"])
    def price_comparison(self, request, pk=None):
        strategy = self.get_object()
        return Response(strategy.price_comparison_data())

    @extend_schema(
        summary="Latest price of the target currency",
        description="The latest exchange rate from the target to the payment currency, and its date.",
        responses=OpenApiTypes.OBJECT,
    )
    @action(detail=True, methods=["get"])
    def current_price(self, request, pk=None):
        strategy = self.get_object()
        price_data = strategy.current_price()
        if price_data:
            price, date = price_data
            return Response({"price": price, "date": date})
        return Response({"price": None, "date": None})


class DCAEntryViewSet(viewsets.ModelViewSet):
    """One buy in a DCA strategy: what was paid and what was received."""

    permission_classes = SHARED_OBJECT_PERMISSIONS
    shared_object_via = "strategy"
    queryset = DCAEntry.objects.all()
    serializer_class = DCAEntrySerializer
    filterset_fields = {
        "strategy": ["exact"],
        "date": ["exact", "gte", "lte", "gt", "lt"],
        "amount_paid": ["exact", "gte", "lte", "gt", "lt"],
        "amount_received": ["exact", "gte", "lte", "gt", "lt"],
        "expense_transaction": ["exact", "isnull"],
        "income_transaction": ["exact", "isnull"],
        "notes": ["exact", "icontains"],
        "created_at": ["exact", "gte", "lte", "gt", "lt"],
        "updated_at": ["exact", "gte", "lte", "gt", "lt"],
    }
    search_fields = ["notes"]
    ordering_fields = "__all__"
    ordering = ["-date"]

    def get_queryset(self):
        # Filter entries by strategies the user has access to
        accessible_strategies = DCAStrategy.objects.all()
        return DCAEntry.objects.filter(strategy__in=accessible_strategies)
