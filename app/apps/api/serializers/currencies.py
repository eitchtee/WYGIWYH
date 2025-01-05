from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated

from apps.currencies.models import Currency, ExchangeRate


class CurrencySerializer(serializers.ModelSerializer):
    permission_classes = [IsAuthenticated]

    class Meta:
        model = Currency
        fields = "__all__"


class ExchangeRateSerializer(serializers.ModelSerializer):
    # For read operations (GET)
    from_currency = CurrencySerializer(read_only=True)

    # For write operations (POST, PUT, PATCH)
    from_currency_id = serializers.PrimaryKeyRelatedField(
        queryset=Currency.objects.all(), source="from_currency", write_only=True
    )

    to_currency = CurrencySerializer(read_only=True)

    # For write operations (POST, PUT, PATCH)
    to_currency_id = serializers.PrimaryKeyRelatedField(
        queryset=Currency.objects.all(), source="to_currency", write_only=True
    )

    permission_classes = [IsAuthenticated]

    class Meta:
        model = ExchangeRate
        fields = "__all__"
