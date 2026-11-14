from decimal import Decimal

from django.db import transaction as db_transaction
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
    SubTransaction,
    QuickTransaction,
)
from apps.common.middleware.thread_local import get_current_user


class SubTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubTransaction
        fields = ["id", "name", "amount"]
        read_only_fields = ["id"]


class SubTransactionsMixin:
    """`sub_transactions`, when sent, replaces the parts; a non-empty list sets
    the amount to their sum. Declare the field on the serializer itself."""

    sub_amount_field = "amount"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields[self.sub_amount_field].required = False

    def is_transfer(self, data):
        return False

    def validate(self, data):
        field = self.sub_amount_field
        subs = data.get("sub_transactions")
        has_parts = self.instance is not None and self.instance.sub_transactions.exists()
        if self.is_transfer(data):
            if subs:
                raise serializers.ValidationError(
                    {"sub_transactions": _("Transfers can't have sub-transactions.")}
                )
            if has_parts:
                data["sub_transactions"] = []
        elif subs:
            data[field] = sum(sub["amount"] for sub in subs)
        elif subs is None and field in data and has_parts:
            raise serializers.ValidationError(
                {
                    field: _(
                        "The amount is the sum of the sub-transactions; "
                        "send sub_transactions instead."
                    )
                }
            )
        if not self.partial and data.get(field) is None:
            raise serializers.ValidationError({field: _("This field is required.")})
        return super().validate(data)

    @staticmethod
    def set_sub_transactions(instance, subs):
        if subs is None:
            return
        instance.sub_transactions.all().delete()
        for sub in subs:
            instance.sub_transactions.create(**sub)

    def create(self, validated_data):
        subs = validated_data.pop("sub_transactions", None)
        with db_transaction.atomic():
            instance = super().create(validated_data)
            self.set_sub_transactions(instance, subs)
            self.after_save(instance, created=True)
        return instance

    def update(self, instance, validated_data):
        subs = validated_data.pop("sub_transactions", None)
        with db_transaction.atomic():
            instance = super().update(instance, validated_data)
            self.set_sub_transactions(instance, subs)
            self.after_save(instance, created=False)
        return instance

    def after_save(self, instance, created):
        """Runs once the parts are saved, e.g. to generate transactions from them."""


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


class InstallmentPlanSerializer(SubTransactionsMixin, serializers.ModelSerializer):
    sub_amount_field = "installment_amount"
    sub_transactions = SubTransactionSerializer(many=True, required=False)
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
            "sub_transactions",
            "category",
            "tags",
            "entities",
            "notes",
        ]
        read_only_fields = ["installment_total_number", "end_date"]

    def after_save(self, instance, created):
        if created:
            instance.create_transactions()
        else:
            instance.update_transactions()


class RecurringTransactionSerializer(SubTransactionsMixin, serializers.ModelSerializer):
    sub_transactions = SubTransactionSerializer(many=True, required=False)
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
            "sub_transactions",
            "to_account",
            "to_amount",
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

    def validate(self, attrs):
        # Same rule as TransferTemplate.clean(), which DRF doesn't run
        type_ = attrs.get("type", getattr(self.instance, "type", None))
        to_account = attrs.get("to_account", getattr(self.instance, "to_account", None))
        if type_ == RecurringTransaction.Type.TRANSFER and not to_account:
            raise serializers.ValidationError(
                {"to_account": _("This field is required.")}
            )
        return super().validate(attrs)

    def is_transfer(self, data):
        type_ = data.get("type", getattr(self.instance, "type", None))
        return type_ == RecurringTransaction.Type.TRANSFER

    def after_save(self, instance, created):
        if created:
            instance.create_upcoming_transactions()
        else:
            instance.update_unpaid_transactions()
            instance.generate_upcoming_transactions()


class TransactionSerializer(SubTransactionsMixin, serializers.ModelSerializer):
    sub_transactions = SubTransactionSerializer(many=True, required=False)
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
            "linked_transaction",
            "installment_id",
            "owner",
            "deleted_at",
            "deleted",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["account_id"].queryset = Account.objects.all()

    def is_transfer(self, data):
        return bool(self.instance and self.instance.linked_transaction_id)

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
        return super().validate(data)

    def create(self, validated_data):
        tags = validated_data.pop("tags", [])
        entities = validated_data.pop("entities", [])
        transaction = super().create(validated_data)
        transaction.tags.set(tags)
        transaction.entities.set(entities)
        return transaction

    def update(self, instance, validated_data):
        tags = validated_data.pop("tags", None)
        entities = validated_data.pop("entities", None)
        instance = super().update(instance, validated_data)

        if tags is not None:
            instance.tags.set(tags)
        if entities is not None:
            instance.entities.set(entities)

        return instance

    @staticmethod
    def get_exchanged_amount(obj) -> Decimal:
        return obj.exchanged_amount()


class QuickTransactionSerializer(SubTransactionsMixin, serializers.ModelSerializer):
    sub_transactions = SubTransactionSerializer(many=True, required=False)
    category: str | int = TransactionCategoryField(required=False)
    tags: str | int = TransactionTagField(required=False)
    entities: str | int = TransactionEntityField(required=False)

    class Meta:
        model = QuickTransaction
        fields = [
            "id",
            "name",
            "account",
            "type",
            "is_paid",
            "mute",
            "amount",
            "sub_transactions",
            "to_account",
            "to_amount",
            "description",
            "notes",
            "category",
            "tags",
            "entities",
            "internal_note",
            "internal_id",
        ]

    def is_transfer(self, data):
        type_ = data.get("type", getattr(self.instance, "type", None))
        return type_ == QuickTransaction.Type.TRANSFER

    def validate(self, attrs):
        # Same rules as the model's, which DRF doesn't run
        name = attrs.get("name", getattr(self.instance, "name", None))
        same_name = QuickTransaction.objects.filter(name=name)
        if self.instance:
            same_name = same_name.exclude(pk=self.instance.pk)
        if same_name.exists():
            raise serializers.ValidationError(
                {"name": _("A quick transaction with this name already exists.")}
            )
        if self.is_transfer(attrs):
            account = attrs.get("account", getattr(self.instance, "account", None))
            to_account = attrs.get("to_account", getattr(self.instance, "to_account", None))
            if not to_account:
                raise serializers.ValidationError(
                    {"to_account": _("This field is required.")}
                )
            if to_account == account:
                raise serializers.ValidationError(
                    {"to_account": _("From and To accounts must be different.")}
                )
        return super().validate(attrs)

