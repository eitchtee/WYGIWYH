from rest_framework import viewsets

from apps.api.serializers import ExchangeRateSerializer
from apps.api.serializers import CurrencySerializer
from apps.currencies.models import Currency
from apps.currencies.models import ExchangeRate


class CurrencyViewSet(viewsets.ModelViewSet):
    queryset = Currency.objects.all()
    serializer_class = CurrencySerializer


class ExchangeRateViewSet(viewsets.ModelViewSet):
    queryset = ExchangeRate.objects.all()
    serializer_class = ExchangeRateSerializer
