from decimal import Decimal

from django.utils.translation import gettext_lazy as _
from drf_spectacular import openapi
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field

from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated

from apps.accounts.models import Account
from apps.api.fields.transactions import (
    TransactionTagField,
    TransactionCategoryField,
    TransactionEntityField,
)
from apps.api.serializers.accounts import AccountSerializer
from apps.transactions.models import (
    Transaction,
    TransactionCategory,
    TransactionTag,
    InstallmentPlan,
    TransactionEntity,
    RecurringTransaction,
)
from apps.common.middleware.thread_local import get_current_user


class TransactionCategorySerializer(serializers.ModelSerializer):
    permission_classes = [IsAuthenticated]

    class Meta:
        model = TransactionCategory
        fields = "__all__"
        read_only_fields = [
            "id",
            "owner",
        ]


class TransactionTagSerializer(serializers.ModelSerializer):
    permission_classes = [IsAuthenticated]

    class Meta:
        model = TransactionTag
        fields = "__all__"
        read_only_fields = [
            "id",
            "owner",
        ]


class TransactionEntitySerializer(serializers.ModelSerializer):
    permission_classes = [IsAuthenticated]

    class Meta:
        model = TransactionEntity
        fields = "__all__"
        read_only_fields = [
            "id",
            "owner",
        ]


class InstallmentPlanSerializer(serializers.ModelSerializer):
    category: str | int = TransactionCategoryField(required=False)
    tags: str | int = TransactionTagField(required=False)
    entities: str | int = TransactionEntityField(required=False)

    permission_classes = [IsAuthenticated]

    class Meta:
        model = InstallmentPlan
        fields = [
            "id",
            "account",
            "type",
            "description",
            "number_of_installments",
            "installment_start",
            "installment_total_number",
            "start_date",
            "reference_date",
            "end_date",
            "recurrence",
            "installment_amount",
            "category",
            "tags",
            "entities",
            "notes",
        ]
        read_only_fields = ["installment_total_number", "end_date"]

    def create(self, validated_data):
        instance = super().create(validated_data)
        instance.create_transactions()
        return instance

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        instance.update_transactions()
        return instance


class RecurringTransactionSerializer(serializers.ModelSerializer):
    category: str | int = TransactionCategoryField(required=False)
    tags: str | int = TransactionTagField(required=False)
    entities: str | int = TransactionEntityField(required=False)

    class Meta:
        model = RecurringTransaction
        fields = [
            "id",
            "is_paused",
            "account",
            "type",
            "amount",
            "description",
            "category",
            "tags",
            "entities",
            "notes",
            "reference_date",
            "start_date",
            "end_date",
            "recurrence_type",
            "recurrence_interval",
            "last_generated_date",
            "last_generated_reference_date",
        ]
        read_only_fields = ["last_generated_date", "last_generated_reference_date"]

    def create(self, validated_data):
        instance = super().create(validated_data)
        instance.create_upcoming_transactions()
        return instance

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        instance.update_unpaid_transactions()
        instance.generate_upcoming_transactions()
        return instance


class TransactionSerializer(serializers.ModelSerializer):
    category: str | int = TransactionCategoryField(required=False)
    tags: str | int = TransactionTagField(required=False)
    entities: str | int = TransactionEntityField(required=False)

    exchanged_amount = serializers.SerializerMethodField()

    # For read operations (GET)
    account = AccountSerializer(read_only=True)

    # For write operations (POST, PUT, PATCH)
    account_id = serializers.PrimaryKeyRelatedField(
        queryset=Account.objects.all(), source="account", write_only=True
    )

    reference_date = serializers.DateField(
        required=False, input_formats=["iso-8601", "%Y-%m"], format="%Y-%m"
    )

    permission_classes = [IsAuthenticated]

    class Meta:
        model = Transaction
        fields = "__all__"
        read_only_fields = [
            "id",
            "installment_plan",
            "recurring_transaction",
            "installment_id",
            "owner",
            "deleted_at",
            "deleted",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["account_id"].queryset = Account.objects.all()

    def validate(self, data):
        if not self.partial:
            if "date" in data and "reference_date" not in data:
                data["reference_date"] = data["date"].replace(day=1)
            elif "reference_date" in data:
                data["reference_date"] = data["reference_date"].replace(day=1)
            else:
                raise serializers.ValidationError(
                    _("Either 'date' or 'reference_date' must be provided.")
                )
        return data

    def create(self, validated_data):
        tags = validated_data.pop("tags", [])
        entities = validated_data.pop("entities", [])
        transaction = Transaction.objects.create(**validated_data)
        transaction.tags.set(tags)
        transaction.entities.set(entities)
        return transaction

    def update(self, instance, validated_data):
        tags = validated_data.pop("tags", None)
        entities = validated_data.pop("entities", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if tags is not None:
            instance.tags.set(tags)
        if entities is not None:
            instance.entities.set(entities)

        return instance

    @staticmethod
    def get_exchanged_amount(obj) -> Decimal:
        return obj.exchanged_amount()
