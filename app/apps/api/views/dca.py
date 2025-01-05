from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.dca.models import DCAStrategy, DCAEntry
from apps.api.serializers import DCAStrategySerializer, DCAEntrySerializer


class DCAStrategyViewSet(viewsets.ModelViewSet):
    queryset = DCAStrategy.objects.all()
    serializer_class = DCAStrategySerializer

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

    def get_queryset(self):
        queryset = DCAEntry.objects.all()
        strategy_id = self.request.query_params.get("strategy", None)
        if strategy_id is not None:
            queryset = queryset.filter(strategy_id=strategy_id)
        return queryset
