from rest_framework import viewsets

from apps.api.serializers import ExchangeRateSerializer
from apps.api.serializers import CurrencySerializer
from apps.currencies.models import Currency
from apps.currencies.models import ExchangeRate


class CurrencyViewSet(viewsets.ModelViewSet):
    queryset = Currency.objects.all()
    serializer_class = CurrencySerializer
    filterset_fields = {
        'name': ['exact', 'icontains'],
        'code': ['exact', 'icontains'],
        'decimal_places': ['exact', 'gte', 'lte', 'gt', 'lt'],
        'prefix': ['exact', 'icontains'],
        'suffix': ['exact', 'icontains'],
        'exchange_currency': ['exact'],
        'is_archived': ['exact'],
    }
    search_fields = '__all__'
    ordering_fields = '__all__'


class ExchangeRateViewSet(viewsets.ModelViewSet):
    queryset = ExchangeRate.objects.all()
    serializer_class = ExchangeRateSerializer
    filterset_fields = {
        'from_currency': ['exact'],
        'to_currency': ['exact'],
        'rate': ['exact', 'gte', 'lte', 'gt', 'lt'],
        'date': ['exact', 'gte', 'lte', 'gt', 'lt'],
        'automatic': ['exact'],
    }
    search_fields = '__all__'
    ordering_fields = '__all__'
