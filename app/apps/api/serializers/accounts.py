from copy import copy
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated

from apps.accounts.models import AccountGroup, Account, InvestmentClass
from apps.api.serializers.currencies import CurrencySerializer
from apps.currencies.models import Currency


class AccountGroupSerializer(serializers.ModelSerializer):
    permission_classes = [IsAuthenticated]

    class Meta:
        model = AccountGroup
        fields = "__all__"


class InvestmentClassSerializer(serializers.ModelSerializer):
    permission_classes = [IsAuthenticated]

    class Meta:
        model = InvestmentClass
        fields = ["id", "name", "target"]

    def validate(self, attrs):
        instance = copy(self.instance) if self.instance else InvestmentClass()
        for name, value in attrs.items():
            setattr(instance, name, value)
        try:
            instance.clean()  # unique name and targets up to 100%
        except DjangoValidationError as e:
            raise serializers.ValidationError(e.message_dict)
        return attrs


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

    investment_class = InvestmentClassSerializer(read_only=True)
    investment_class_id = serializers.PrimaryKeyRelatedField(
        queryset=InvestmentClass.objects.all(),
        source="investment_class",
        write_only=True,
        allow_null=True,
        required=False,
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
            "is_investment",
            "investment_class",
            "investment_class_id",
            "income_entities",
            "income_categories",
            "income_tags",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            # Reload the queryset to get an updated version with the requesting user
            self.fields["group_id"].queryset = AccountGroup.objects.all()
            self.fields["investment_class_id"].queryset = InvestmentClass.objects.all()

    def create(self, validated_data):
        return Account.objects.create(**validated_data)

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class AccountBalanceSerializer(serializers.Serializer):
    """Serializer for account balance response."""

    current_balance = serializers.DecimalField(max_digits=20, decimal_places=10)
    projected_balance = serializers.DecimalField(max_digits=20, decimal_places=10)
    currency = CurrencySerializer()



class InvestmentPerformanceSerializer(serializers.Serializer):
    """Serializer for an investment account's performance."""

    currency = CurrencySerializer()
    priced = serializers.BooleanField()
    quantity = serializers.DecimalField(max_digits=42, decimal_places=30)
    price = serializers.DecimalField(max_digits=42, decimal_places=30, allow_null=True)
    price_date = serializers.DateTimeField(allow_null=True)
    average_cost = serializers.DecimalField(
        max_digits=42, decimal_places=30, allow_null=True
    )
    cost_basis = serializers.DecimalField(max_digits=42, decimal_places=30)
    market_value = serializers.DecimalField(
        max_digits=42, decimal_places=30, allow_null=True
    )
    unrealized = serializers.DecimalField(
        max_digits=42, decimal_places=30, allow_null=True
    )
    realized = serializers.DecimalField(max_digits=42, decimal_places=30)
    income = serializers.DecimalField(max_digits=42, decimal_places=30)
    contributed = serializers.DecimalField(max_digits=42, decimal_places=30)
    withdrawn = serializers.DecimalField(max_digits=42, decimal_places=30)
    total_return = serializers.DecimalField(max_digits=42, decimal_places=30)
    return_percentage = serializers.DecimalField(
        max_digits=42, decimal_places=30, allow_null=True
    )
    estimated = serializers.BooleanField()
    money_weighted_return = serializers.SerializerMethodField(
        help_text="Return weighted by when money went in and out, in percent: "
        "annual (XIRR) when the first contribution is a year old or more, "
        "otherwise over the period held."
    )
    money_weighted_annualized = serializers.SerializerMethodField()

    def get_money_weighted_return(self, perf) -> Decimal | None:
        return perf.money_weighted and perf.money_weighted["percentage"]

    def get_money_weighted_annualized(self, perf) -> bool | None:
        return perf.money_weighted and perf.money_weighted["annualized"]
