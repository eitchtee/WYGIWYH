from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.dca.models import DCAStrategy, DCAEntry
from apps.api.serializers import DCAStrategySerializer, DCAEntrySerializer


class DCAStrategyViewSet(viewsets.ModelViewSet):
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

    def get_queryset(self):
        return DCAStrategy.objects.all().order_by("id")

    @action(detail=True, methods=["get"])
    def investment_frequency(self, request, pk=None):
        strategy = self.get_object()
        return Response(strategy.investment_frequency_data())

    @action(detail=True, methods=["get"])
    def price_comparison(self, request, pk=None):
        strategy = self.get_object()
        return Response(strategy.price_comparison_data())

    @action(detail=True, methods=["get"])
    def current_price(self, request, pk=None):
        strategy = self.get_object()
        price_data = strategy.current_price()
        if price_data:
            price, date = price_data
            return Response({"price": price, "date": date})
        return Response({"price": None, "date": None})


class DCAEntryViewSet(viewsets.ModelViewSet):
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
    search_fields = ['notes']
    ordering_fields = '__all__'
    ordering = ['-date']
