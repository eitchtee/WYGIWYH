from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated

from apps.currencies.models import Currency, ExchangeRate


class CurrencySerializer(serializers.ModelSerializer):
    permission_classes = [IsAuthenticated]

    class Meta:
        model = Currency
        fields = "__all__"
        # Prefixes and suffixes carry their spacing, e.g. "R$ "
        extra_kwargs = {
            "prefix": {"trim_whitespace": False},
            "suffix": {"trim_whitespace": False},
        }


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

    def validate_rate(self, value):
        if value <= 0:
            raise serializers.ValidationError(_("The rate must be greater than zero."))
        return value
