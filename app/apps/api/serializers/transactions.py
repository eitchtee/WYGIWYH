from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated

from apps.accounts.models import Account
from apps.api.serializers.accounts import AccountSerializer
from apps.transactions.models import (
    Transaction,
    TransactionCategory,
    TransactionTag,
    InstallmentPlan,
)


# Create serializers for other related models as needed
class TransactionCategorySerializer(serializers.ModelSerializer):
    permission_classes = [IsAuthenticated]

    class Meta:
        model = TransactionCategory
        fields = "__all__"


class TransactionTagSerializer(serializers.ModelSerializer):
    permission_classes = [IsAuthenticated]

    class Meta:
        model = TransactionTag
        fields = "__all__"


class InstallmentPlanSerializer(serializers.ModelSerializer):
    permission_classes = [IsAuthenticated]

    class Meta:
        model = InstallmentPlan
        fields = "__all__"


class TransactionSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    tags = TransactionTagSerializer(many=True, read_only=True)
    exchanged_amount = serializers.SerializerMethodField()

    # For read operations (GET)
    account = AccountSerializer(read_only=True)

    # For write operations (POST, PUT, PATCH)
    account_id = serializers.PrimaryKeyRelatedField(
        queryset=Account.objects.all(), source="account", write_only=True
    )

    permission_classes = [IsAuthenticated]

    class Meta:
        model = Transaction
        fields = "__all__"

    @staticmethod
    def get_exchanged_amount(obj):
        return obj.exchanged_amount()
