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

    def perform_create(self, serializer):
        instance = serializer.save()
        transaction_created.send(sender=instance)

    def perform_update(self, serializer):
        instance = serializer.save()
        transaction_updated.send(sender=instance)

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    def get_queryset(self):
        return Transaction.objects.all().order_by("-id")


class TransactionCategoryViewSet(viewsets.ModelViewSet):
    queryset = TransactionCategory.objects.all()
    serializer_class = TransactionCategorySerializer
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        return TransactionCategory.objects.all().order_by("id")


class TransactionTagViewSet(viewsets.ModelViewSet):
    queryset = TransactionTag.objects.all()
    serializer_class = TransactionTagSerializer
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        return TransactionTag.objects.all().order_by("id")


class TransactionEntityViewSet(viewsets.ModelViewSet):
    queryset = TransactionEntity.objects.all()
    serializer_class = TransactionEntitySerializer
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        return TransactionEntity.objects.all().order_by("id")


class InstallmentPlanViewSet(viewsets.ModelViewSet):
    queryset = InstallmentPlan.objects.all()
    serializer_class = InstallmentPlanSerializer
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        return InstallmentPlan.objects.all().order_by("-id")


class RecurringTransactionViewSet(viewsets.ModelViewSet):
    queryset = RecurringTransaction.objects.all()
    serializer_class = RecurringTransactionSerializer
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        return RecurringTransaction.objects.all().order_by("-id")
