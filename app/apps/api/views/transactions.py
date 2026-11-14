from copy import deepcopy

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.api.serializers import (
    TransactionSerializer,
    TransactionCategorySerializer,
    TransactionTagSerializer,
    InstallmentPlanSerializer,
    TransactionEntitySerializer,
    RecurringTransactionSerializer,
    QuickTransactionSerializer,
)
from apps.transactions.models import (
    Transaction,
    TransactionCategory,
    TransactionTag,
    InstallmentPlan,
    TransactionEntity,
    RecurringTransaction,
    QuickTransaction,
)
from apps.rules.signals import transaction_updated, transaction_created
from apps.api.permissions import SHARED_OBJECT_PERMISSIONS


class TransactionViewSet(viewsets.ModelViewSet):
    queryset = Transaction.objects.all()
    serializer_class = TransactionSerializer
    filterset_fields = {
        "account": ["exact"],
        "type": ["exact"],
        "is_paid": ["exact"],
        "date": ["exact", "gte", "lte", "gt", "lt"],
        "reference_date": ["exact", "gte", "lte", "gt", "lt"],
        "mute": ["exact"],
        "amount": ["exact", "gte", "lte", "gt", "lt"],
        "description": ["exact", "icontains"],
        "notes": ["exact", "icontains"],
        "category": ["exact", "isnull"],
        "installment_plan": ["exact", "isnull"],
        "installment_id": ["exact", "gte", "lte"],
        "recurring_transaction": ["exact", "isnull"],
        "internal_note": ["exact", "icontains"],
        "internal_id": ["exact"],
        "deleted": ["exact"],
        "created_at": ["exact", "gte", "lte", "gt", "lt"],
        "updated_at": ["exact", "gte", "lte", "gt", "lt"],
        "deleted_at": ["exact", "gte", "lte", "gt", "lt", "isnull"],
        "owner": ["exact"],
    }
    search_fields = ["description", "notes", "internal_note"]
    ordering_fields = "__all__"
    ordering = ["-id"]

    def get_queryset(self):
        return Transaction.objects.prefetch_related("sub_transactions")

    def perform_create(self, serializer):
        instance = serializer.save()
        transaction_created.send(sender=instance)

    def perform_update(self, serializer):
        old_data = deepcopy(self.get_object())
        instance = serializer.save()
        transaction_updated.send(sender=instance, old_data=old_data)

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)


class TransactionCategoryViewSet(viewsets.ModelViewSet):
    permission_classes = SHARED_OBJECT_PERMISSIONS
    queryset = TransactionCategory.objects.all()
    serializer_class = TransactionCategorySerializer
    filterset_fields = {
        "name": ["exact", "icontains"],
        "mute": ["exact"],
        "active": ["exact"],
        "owner": ["exact"],
    }
    search_fields = ["name"]
    ordering_fields = "__all__"
    ordering = ["id"]

    def get_queryset(self):
        return TransactionCategory.objects.all()


class TransactionTagViewSet(viewsets.ModelViewSet):
    permission_classes = SHARED_OBJECT_PERMISSIONS
    queryset = TransactionTag.objects.all()
    serializer_class = TransactionTagSerializer
    filterset_fields = {
        "name": ["exact", "icontains"],
        "active": ["exact"],
        "owner": ["exact"],
    }
    search_fields = ["name"]
    ordering_fields = "__all__"
    ordering = ["id"]

    def get_queryset(self):
        return TransactionTag.objects.all()


class TransactionEntityViewSet(viewsets.ModelViewSet):
    permission_classes = SHARED_OBJECT_PERMISSIONS
    queryset = TransactionEntity.objects.all()
    serializer_class = TransactionEntitySerializer
    filterset_fields = {
        "name": ["exact", "icontains"],
        "active": ["exact"],
        "owner": ["exact"],
    }
    search_fields = ["name"]
    ordering_fields = "__all__"
    ordering = ["id"]

    def get_queryset(self):
        return TransactionEntity.objects.all()


class InstallmentPlanViewSet(viewsets.ModelViewSet):
    queryset = InstallmentPlan.objects.all()
    serializer_class = InstallmentPlanSerializer
    filterset_fields = {
        "account": ["exact"],
        "type": ["exact"],
        "description": ["exact", "icontains"],
        "number_of_installments": ["exact", "gte", "lte", "gt", "lt"],
        "installment_start": ["exact", "gte", "lte", "gt", "lt"],
        "installment_total_number": ["exact", "gte", "lte", "gt", "lt"],
        "start_date": ["exact", "gte", "lte", "gt", "lt"],
        "reference_date": ["exact", "gte", "lte", "gt", "lt", "isnull"],
        "end_date": ["exact", "gte", "lte", "gt", "lt", "isnull"],
        "recurrence": ["exact"],
        "installment_amount": ["exact", "gte", "lte", "gt", "lt"],
        "category": ["exact", "isnull"],
        "notes": ["exact", "icontains"],
        "add_description_to_transaction": ["exact"],
        "add_notes_to_transaction": ["exact"],
    }
    search_fields = ["description", "notes"]
    ordering_fields = "__all__"
    ordering = ["-id"]

    def get_queryset(self):
        return InstallmentPlan.objects.prefetch_related("sub_transactions")


class RecurringTransactionViewSet(viewsets.ModelViewSet):
    queryset = RecurringTransaction.objects.all()
    serializer_class = RecurringTransactionSerializer
    filterset_fields = {
        "is_paused": ["exact"],
        "account": ["exact"],
        "type": ["exact"],
        "amount": ["exact", "gte", "lte", "gt", "lt"],
        "description": ["exact", "icontains"],
        "category": ["exact", "isnull"],
        "notes": ["exact", "icontains"],
        "reference_date": ["exact", "gte", "lte", "gt", "lt", "isnull"],
        "start_date": ["exact", "gte", "lte", "gt", "lt"],
        "end_date": ["exact", "gte", "lte", "gt", "lt", "isnull"],
        "recurrence_type": ["exact"],
        "recurrence_interval": ["exact", "gte", "lte", "gt", "lt"],
        "keep_at_most": ["exact", "gte", "lte", "gt", "lt"],
        "last_generated_date": ["exact", "gte", "lte", "gt", "lt", "isnull"],
        "last_generated_reference_date": ["exact", "gte", "lte", "gt", "lt", "isnull"],
        "add_description_to_transaction": ["exact"],
        "add_notes_to_transaction": ["exact"],
    }
    search_fields = ["description", "notes"]
    ordering_fields = "__all__"
    ordering = ["-id"]

    def get_queryset(self):
        return RecurringTransaction.objects.prefetch_related("sub_transactions")


class QuickTransactionViewSet(viewsets.ModelViewSet):
    queryset = QuickTransaction.objects.all()
    serializer_class = QuickTransactionSerializer
    filterset_fields = {
        "name": ["exact", "icontains"],
        "account": ["exact"],
        "type": ["exact"],
        "amount": ["exact", "gte", "lte", "gt", "lt"],
        "description": ["exact", "icontains"],
        "category": ["exact", "isnull"],
    }
    search_fields = ["name", "description", "notes"]
    ordering_fields = "__all__"
    ordering = ["name"]

    def get_queryset(self):
        return QuickTransaction.objects.prefetch_related("sub_transactions")

    @action(detail=True, methods=["post"], serializer_class=TransactionSerializer)
    def use(self, request, pk=None):
        """Creates today's transaction from this quick transaction, like its button
        in the app. For a transfer, returns the "from" (expense) side."""
        new_transaction, to_transaction = self.get_object().create_transaction()
        transaction_created.send(sender=new_transaction)
        if to_transaction:
            transaction_created.send(sender=to_transaction)
        return Response(
            TransactionSerializer(new_transaction, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )

