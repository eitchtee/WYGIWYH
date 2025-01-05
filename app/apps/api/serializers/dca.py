from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated

from apps.dca.models import DCAEntry, DCAStrategy


class DCAEntrySerializer(serializers.ModelSerializer):
    profit_loss = serializers.DecimalField(
        max_digits=42, decimal_places=30, read_only=True
    )
    profit_loss_percentage = serializers.DecimalField(
        max_digits=42, decimal_places=30, read_only=True
    )
    current_value = serializers.DecimalField(
        max_digits=42, decimal_places=30, read_only=True
    )
    entry_price = serializers.DecimalField(
        max_digits=42, decimal_places=30, read_only=True
    )

    permission_classes = [IsAuthenticated]

    class Meta:
        model = DCAEntry
        fields = [
            "id",
            "strategy",
            "date",
            "amount_paid",
            "amount_received",
            "notes",
            "created_at",
            "updated_at",
            "profit_loss",
            "profit_loss_percentage",
            "current_value",
            "entry_price",
        ]
        read_only_fields = ["created_at", "updated_at"]


class DCAStrategySerializer(serializers.ModelSerializer):
    entries = DCAEntrySerializer(many=True, read_only=True)
    total_invested = serializers.DecimalField(
        max_digits=42, decimal_places=30, read_only=True
    )
    total_received = serializers.DecimalField(
        max_digits=42, decimal_places=30, read_only=True
    )
    average_entry_price = serializers.DecimalField(
        max_digits=42, decimal_places=30, read_only=True
    )
    total_entries = serializers.IntegerField(read_only=True)
    current_total_value = serializers.DecimalField(
        max_digits=42, decimal_places=30, read_only=True
    )
    total_profit_loss = serializers.DecimalField(
        max_digits=42, decimal_places=30, read_only=True
    )
    total_profit_loss_percentage = serializers.DecimalField(
        max_digits=42, decimal_places=30, read_only=True
    )

    permission_classes = [IsAuthenticated]

    class Meta:
        model = DCAStrategy
        fields = [
            "id",
            "name",
            "target_currency",
            "payment_currency",
            "notes",
            "created_at",
            "updated_at",
            "entries",
            "total_invested",
            "total_received",
            "average_entry_price",
            "total_entries",
            "current_total_value",
            "total_profit_loss",
            "total_profit_loss_percentage",
        ]
        read_only_fields = ["created_at", "updated_at"]
