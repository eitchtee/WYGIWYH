from django.db.models import Q
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated

from apps.api.serializers.currencies import CurrencySerializer
from apps.accounts.models import AccountGroup, Account
from apps.currencies.models import Currency


class AccountGroupSerializer(serializers.ModelSerializer):
    permission_classes = [IsAuthenticated]

    class Meta:
        model = AccountGroup
        fields = "__all__"


class AccountSerializer(serializers.ModelSerializer):
    group = AccountGroupSerializer(read_only=True)
    group_id = serializers.PrimaryKeyRelatedField(
        queryset=AccountGroup.objects.all(),
        source="group",
        write_only=True,
        allow_null=True,
    )

    currency = CurrencySerializer(read_only=True)
    currency_id = serializers.PrimaryKeyRelatedField(
        queryset=Currency.objects.all(), source="currency", write_only=True
    )
    exchange_currency = CurrencySerializer(read_only=True)
    exchange_currency_id = serializers.PrimaryKeyRelatedField(
        queryset=Currency.objects.all(),
        source="exchange_currency",
        write_only=True,
        allow_null=True,
    )

    permission_classes = [IsAuthenticated]

    class Meta:
        model = Account
        fields = [
            "id",
            "name",
            "group",
            "group_id",
            "currency",
            "currency_id",
            "exchange_currency",
            "exchange_currency_id",
            "is_asset",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            # Reload the queryset to get an updated version with the requesting user
            self.fields["group_id"].queryset = AccountGroup.objects.all()

    def create(self, validated_data):
        return Account.objects.create(**validated_data)

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance
