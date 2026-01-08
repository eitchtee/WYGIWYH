from copy import deepcopy

from rest_framework import viewsets

from apps.api.custom.pagination import CustomPageNumberPagination
from apps.api.serializers import (
    TransactionSerializer,
    TransactionCategorySerializer,
    TransactionTagSerializer,
    InstallmentPlanSerializer,
    TransactionEntitySerializer,
    RecurringTransactionSerializer,
)
from apps.transactions.models import (
    Transaction,
    TransactionCategory,
    TransactionTag,
    InstallmentPlan,
    TransactionEntity,
    RecurringTransaction,
)
from apps.rules.signals import transaction_updated, transaction_created


class TransactionViewSet(viewsets.ModelViewSet):
    queryset = Transaction.objects.all()
    serializer_class = TransactionSerializer
    pagination_class = CustomPageNumberPagination
    filterset_fields = {
        'account': ['exact'],
        'type': ['exact'],
        'is_paid': ['exact'],
        'date': ['exact', 'gte', 'lte', 'gt', 'lt'],
        'reference_date': ['exact', 'gte', 'lte', 'gt', 'lt'],
        'mute': ['exact'],
        'amount': ['exact', 'gte', 'lte', 'gt', 'lt'],
        'description': ['exact', 'icontains'],
        'notes': ['exact', 'icontains'],
        'category': ['exact', 'isnull'],
        'installment_plan': ['exact', 'isnull'],
        'installment_id': ['exact', 'gte', 'lte'],
        'recurring_transaction': ['exact', 'isnull'],
        'internal_note': ['exact', 'icontains'],
        'internal_id': ['exact'],
        'deleted': ['exact'],
        'created_at': ['exact', 'gte', 'lte', 'gt', 'lt'],
        'updated_at': ['exact', 'gte', 'lte', 'gt', 'lt'],
        'deleted_at': ['exact', 'gte', 'lte', 'gt', 'lt', 'isnull'],
        'owner': ['exact'],
    }
    search_fields = ['description', 'notes', 'internal_note']
    ordering_fields = '__all__'
    ordering = ['-id']

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
    queryset = TransactionCategory.objects.all()
    serializer_class = TransactionCategorySerializer
    pagination_class = CustomPageNumberPagination
    filterset_fields = {
        'name': ['exact', 'icontains'],
        'mute': ['exact'],
        'active': ['exact'],
        'owner': ['exact'],
    }
    search_fields = ['name']
    ordering_fields = '__all__'
    ordering = ['id']


class TransactionTagViewSet(viewsets.ModelViewSet):
    queryset = TransactionTag.objects.all()
    serializer_class = TransactionTagSerializer
    pagination_class = CustomPageNumberPagination
    filterset_fields = {
        'name': ['exact', 'icontains'],
        'active': ['exact'],
        'owner': ['exact'],
    }
    search_fields = ['name']
    ordering_fields = '__all__'
    ordering = ['id']


class TransactionEntityViewSet(viewsets.ModelViewSet):
    queryset = TransactionEntity.objects.all()
    serializer_class = TransactionEntitySerializer
    pagination_class = CustomPageNumberPagination
    filterset_fields = {
        'name': ['exact', 'icontains'],
        'active': ['exact'],
        'owner': ['exact'],
    }
    search_fields = ['name']
    ordering_fields = '__all__'
    ordering = ['id']


class InstallmentPlanViewSet(viewsets.ModelViewSet):
    queryset = InstallmentPlan.objects.all()
    serializer_class = InstallmentPlanSerializer
    pagination_class = CustomPageNumberPagination
    filterset_fields = {
        'account': ['exact'],
        'type': ['exact'],
        'description': ['exact', 'icontains'],
        'number_of_installments': ['exact', 'gte', 'lte', 'gt', 'lt'],
        'installment_start': ['exact', 'gte', 'lte', 'gt', 'lt'],
        'installment_total_number': ['exact', 'gte', 'lte', 'gt', 'lt'],
        'start_date': ['exact', 'gte', 'lte', 'gt', 'lt'],
        'reference_date': ['exact', 'gte', 'lte', 'gt', 'lt', 'isnull'],
        'end_date': ['exact', 'gte', 'lte', 'gt', 'lt', 'isnull'],
        'recurrence': ['exact'],
        'installment_amount': ['exact', 'gte', 'lte', 'gt', 'lt'],
        'category': ['exact', 'isnull'],
        'notes': ['exact', 'icontains'],
        'add_description_to_transaction': ['exact'],
        'add_notes_to_transaction': ['exact'],
    }
    search_fields = ['description', 'notes']
    ordering_fields = '__all__'
    ordering = ['-id']


class RecurringTransactionViewSet(viewsets.ModelViewSet):
    queryset = RecurringTransaction.objects.all()
    serializer_class = RecurringTransactionSerializer
    pagination_class = CustomPageNumberPagination
    filterset_fields = {
        'is_paused': ['exact'],
        'account': ['exact'],
        'type': ['exact'],
        'amount': ['exact', 'gte', 'lte', 'gt', 'lt'],
        'description': ['exact', 'icontains'],
        'category': ['exact', 'isnull'],
        'notes': ['exact', 'icontains'],
        'reference_date': ['exact', 'gte', 'lte', 'gt', 'lt', 'isnull'],
        'start_date': ['exact', 'gte', 'lte', 'gt', 'lt'],
        'end_date': ['exact', 'gte', 'lte', 'gt', 'lt', 'isnull'],
        'recurrence_type': ['exact'],
        'recurrence_interval': ['exact', 'gte', 'lte', 'gt', 'lt'],
        'keep_at_most': ['exact', 'gte', 'lte', 'gt', 'lt'],
        'last_generated_date': ['exact', 'gte', 'lte', 'gt', 'lt', 'isnull'],
        'last_generated_reference_date': ['exact', 'gte', 'lte', 'gt', 'lt', 'isnull'],
        'add_description_to_transaction': ['exact'],
        'add_notes_to_transaction': ['exact'],
    }
    search_fields = ['description', 'notes']
    ordering_fields = '__all__'
    ordering = ['-id']

