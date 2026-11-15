from copy import deepcopy

from django.db.models import Count, Sum
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

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
from apps.api.permissions import SHARED_OBJECT_PERMISSIONS

# group_by -> (id field, name field)
SUMMARY_GROUPS = {
    "category": ("category__id", "category__name"),
    "tag": ("tags__id", "tags__name"),
    "entity": ("entities__id", "entities__name"),
    "account": ("account__id", "account__name"),
    "month": (None, "reference_date"),
}


class TransactionViewSet(viewsets.ModelViewSet):
    """Income (`IN`) and expense (`EX`) entries. `amount` is never negative;
    `type` gives the direction. `amount` is required unless `sub_transactions` is
    sent; then it's their sum. `reference_date` is the month the transaction
    counts toward, which may differ from `date`. Transfers are an expense and
    an income linked through `linked_transaction`; deleting one deletes both."""

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
        "tags": ["exact"],
        "entities": ["exact"],
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

    @extend_schema(
        summary="Sum transactions",
        description=(
            "Totals and counts of the transactions matching the same filters as "
            "the list, split by currency and type, optionally grouped. Muted "
            "transactions and those in muted categories are left out unless "
            "`include_muted` is true. Grouping by tag or entity counts a "
            "transaction once per tag/entity; untagged ones have a null group."
        ),
        parameters=[
            OpenApiParameter("group_by", enum=list(SUMMARY_GROUPS)),
            OpenApiParameter("include_muted", OpenApiTypes.BOOL),
        ],
        responses=inline_serializer(
            "TransactionSummaryRow",
            {
                "currency": serializers.CharField(),
                "type": serializers.CharField(),
                "group": serializers.CharField(allow_null=True, required=False),
                "group_id": serializers.IntegerField(allow_null=True, required=False),
                "total": serializers.DecimalField(max_digits=42, decimal_places=30),
                "count": serializers.IntegerField(),
            },
            many=True,
        ),
    )
    @action(detail=False, methods=["get"], pagination_class=None)
    def summary(self, request):
        group_by = request.query_params.get("group_by")
        if group_by and group_by not in SUMMARY_GROUPS:
            raise ValidationError(
                {"group_by": f"Must be one of: {', '.join(SUMMARY_GROUPS)}."}
            )

        queryset = self.filter_queryset(self.get_queryset())
        if request.query_params.get("include_muted", "").lower() != "true":
            queryset = queryset.exclude(mute=True).exclude(category__mute=True)

        id_field, group_field = SUMMARY_GROUPS.get(group_by, (None, None))
        fields = ["account__currency__code", "type"] + [
            f for f in (id_field, group_field) if f
        ]
        rows = (
            queryset.order_by()  # the default ordering would split the groups
            .values(*fields)
            .annotate(total=Sum("amount"), count=Count("id"))
            # by group first, so months come out in order
            .order_by(*[f for f in (group_field,) if f], "account__currency__code", "type")
        )

        data = []
        for row in rows:
            item = {
                "currency": row["account__currency__code"],
                "type": row["type"],
                "total": row["total"],
                "count": row["count"],
            }
            if group_field:
                group = row[group_field]
                item["group"] = group.strftime("%Y-%m") if group_by == "month" and group else group
            if id_field:
                item["group_id"] = row[id_field]
            data.append(item)
        return Response(data)


class TransactionCategoryViewSet(viewsets.ModelViewSet):
    """Categories, one per transaction. Transactions in a muted category are left out of totals. Sending a category name that doesn't exist on a transaction creates it."""

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
    """Tags; a transaction can have many. Sending a tag name that doesn't exist on a transaction creates it."""

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
    """Entities are the people or businesses on the other side of a transaction. Sending an entity name that doesn't exist on a transaction creates it."""

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
    """A purchase split into a fixed number of installments. Saving a plan creates or updates one transaction per installment. `installment_amount` is required unless `sub_transactions` is sent; then it's their sum."""

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
    """A transaction or transfer that repeats on a schedule. Saving one generates its upcoming transactions and updates the unpaid ones. `amount` is required unless `sub_transactions` is sent; then it's their sum."""

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
