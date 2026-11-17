from functools import reduce
from operator import or_

from django.db.models import Prefetch, Q
from import_export import fields, resources
from import_export.widgets import ForeignKeyWidget

from apps.accounts.models import Account
from apps.export_app.widgets.foreign_key import (
    AllObjectsForeignKeyWidget,
    AutoCreateForeignKeyWidget,
)
from apps.export_app.widgets.many_to_many import AutoCreateManyToManyWidget
from apps.export_app.widgets.string import EmptyStringToNoneField
from apps.transactions.models import (
    Transaction,
    TransactionCategory,
    TransactionTag,
    TransactionEntity,
    RecurringTransaction,
    InstallmentPlan,
    QuickTransaction,
    SubTransaction,
)
from apps.export_app.widgets.numbers import UniversalDecimalWidget


def with_relations(queryset, *related):
    """Loads relations up front, and every owner's tags and entities, not just the exporter's."""
    return queryset.select_related(*related).prefetch_related(
        Prefetch("tags", queryset=TransactionTag.all_objects.all()),
        Prefetch("entities", queryset=TransactionEntity.all_objects.all()),
    )


class PrefetchedExportResource(resources.ModelResource):
    def iter_queryset(self, queryset):
        # import-export pages prefetched querysets with OFFSET, which slows down
        # quadratically; Django's iterator prefetches per chunk with a cursor instead
        yield from queryset.iterator(chunk_size=2000)


class TransactionResource(PrefetchedExportResource):
    account = fields.Field(
        attribute="account",
        column_name="account",
        widget=AllObjectsForeignKeyWidget(Account, "name"),
    )

    category = fields.Field(
        attribute="category",
        column_name="category",
        widget=AutoCreateForeignKeyWidget(TransactionCategory, "name"),
    )

    tags = fields.Field(
        attribute="tags",
        column_name="tags",
        widget=AutoCreateManyToManyWidget(TransactionTag, field="name"),
    )

    entities = fields.Field(
        attribute="entities",
        column_name="entities",
        widget=AutoCreateManyToManyWidget(TransactionEntity, field="name"),
    )

    internal_id = EmptyStringToNoneField(
        column_name="internal_id", attribute="internal_id"
    )

    amount = fields.Field(
        attribute="amount",
        column_name="amount",
        widget=UniversalDecimalWidget(),
    )

    class Meta:
        model = Transaction

    def get_queryset(self):
        return with_relations(
            Transaction.userless_all_objects.all(),
            "account",
            "owner",
            "category",
            "installment_plan",
            "recurring_transaction",
            "linked_transaction",
        )


class TransactionTagResource(resources.ModelResource):
    class Meta:
        model = TransactionTag

    def get_queryset(self):
        return TransactionTag.all_objects.all()


class TransactionEntityResource(resources.ModelResource):
    class Meta:
        model = TransactionEntity

    def get_queryset(self):
        return TransactionEntity.all_objects.all()


class TransactionCategoyResource(resources.ModelResource):
    class Meta:
        model = TransactionCategory

    def get_queryset(self):
        return TransactionCategory.all_objects.all()


class RecurringTransactionResource(PrefetchedExportResource):
    account = fields.Field(
        attribute="account",
        column_name="account",
        widget=AllObjectsForeignKeyWidget(Account, "name"),
    )

    category = fields.Field(
        attribute="category",
        column_name="category",
        widget=AutoCreateForeignKeyWidget(TransactionCategory, "name"),
    )

    tags = fields.Field(
        attribute="tags",
        column_name="tags",
        widget=AutoCreateManyToManyWidget(TransactionTag, field="name"),
    )

    entities = fields.Field(
        attribute="entities",
        column_name="entities",
        widget=AutoCreateManyToManyWidget(TransactionEntity, field="name"),
    )

    amount = fields.Field(
        attribute="amount",
        column_name="amount",
        widget=UniversalDecimalWidget(),
    )

    # Lets restore find the account and its names under the right user
    account_owner = fields.Field(column_name="account_owner", readonly=True)

    class Meta:
        model = RecurringTransaction

    def get_queryset(self):
        return with_relations(
            RecurringTransaction.all_objects.all(), "account", "to_account", "category"
        )

    def dehydrate_account_owner(self, obj):
        """Export the account's owner ID for proper import matching."""
        return obj.account.owner_id if obj.account else None


class InstallmentPlanResource(PrefetchedExportResource):
    account = fields.Field(
        attribute="account",
        column_name="account",
        widget=AllObjectsForeignKeyWidget(Account, "name"),
    )

    category = fields.Field(
        attribute="category",
        column_name="category",
        widget=AutoCreateForeignKeyWidget(TransactionCategory, "name"),
    )

    tags = fields.Field(
        attribute="tags",
        column_name="tags",
        widget=AutoCreateManyToManyWidget(TransactionTag, field="name"),
    )

    entities = fields.Field(
        attribute="entities",
        column_name="entities",
        widget=AutoCreateManyToManyWidget(TransactionEntity, field="name"),
    )

    installment_amount = fields.Field(
        attribute="installment_amount",
        column_name="installment_amount",
        widget=UniversalDecimalWidget(),
    )

    # Lets restore find the account and its names under the right user
    account_owner = fields.Field(column_name="account_owner", readonly=True)

    class Meta:
        model = InstallmentPlan

    def get_queryset(self):
        return with_relations(
            InstallmentPlan.all_objects.all(), "account", "category"
        )

    def dehydrate_account_owner(self, obj):
        """Export the account's owner ID for proper import matching."""
        return obj.account.owner_id if obj.account else None


class AnyOwnerForeignKeyWidget(ForeignKeyWidget):
    """Finds the parent among every user's rows, soft-deleted ones included."""

    def get_queryset(self, value, row, *args, **kwargs):
        return self.model._base_manager.all()


class QuickTransactionResource(PrefetchedExportResource):
    account = fields.Field(
        attribute="account",
        column_name="account",
        widget=AllObjectsForeignKeyWidget(Account, "name"),
    )
    to_account = fields.Field(
        attribute="to_account",
        column_name="to_account",
        widget=AllObjectsForeignKeyWidget(Account, "name"),
    )
    category = fields.Field(
        attribute="category",
        column_name="category",
        widget=AutoCreateForeignKeyWidget(TransactionCategory, "name"),
    )
    tags = fields.Field(
        attribute="tags",
        column_name="tags",
        widget=AutoCreateManyToManyWidget(TransactionTag, field="name"),
    )
    entities = fields.Field(
        attribute="entities",
        column_name="entities",
        widget=AutoCreateManyToManyWidget(TransactionEntity, field="name"),
    )
    internal_id = EmptyStringToNoneField(
        column_name="internal_id", attribute="internal_id"
    )
    amount = fields.Field(
        attribute="amount",
        column_name="amount",
        widget=UniversalDecimalWidget(),
    )
    to_amount = fields.Field(
        attribute="to_amount",
        column_name="to_amount",
        widget=UniversalDecimalWidget(),
    )

    class Meta:
        model = QuickTransaction

    def get_queryset(self):
        return with_relations(
            QuickTransaction.all_objects.all(), "account", "to_account", "category", "owner"
        )


SUB_TRANSACTION_BACKUP_PARENTS = (
    "transaction",
    "installment_plan",
    "recurring_transaction",
    "quick_transaction",
)


class SubTransactionResource(resources.ModelResource):
    transaction = fields.Field(
        attribute="transaction",
        column_name="transaction",
        widget=AnyOwnerForeignKeyWidget(Transaction),
    )
    installment_plan = fields.Field(
        attribute="installment_plan",
        column_name="installment_plan",
        widget=AnyOwnerForeignKeyWidget(InstallmentPlan),
    )
    recurring_transaction = fields.Field(
        attribute="recurring_transaction",
        column_name="recurring_transaction",
        widget=AnyOwnerForeignKeyWidget(RecurringTransaction),
    )
    quick_transaction = fields.Field(
        attribute="quick_transaction",
        column_name="quick_transaction",
        widget=AnyOwnerForeignKeyWidget(QuickTransaction),
    )
    amount = fields.Field(
        attribute="amount",
        column_name="amount",
        widget=UniversalDecimalWidget(),
    )

    def __init__(self, parents=SUB_TRANSACTION_BACKUP_PARENTS, **kwargs):
        """`parents`: the kinds of parent being exported, whose parts go along."""
        super().__init__(**kwargs)
        self.parents = parents

    class Meta:
        model = SubTransaction

    def get_queryset(self):
        return SubTransaction.objects.filter(
            reduce(or_, (Q(**{f"{p}__isnull": False}) for p in self.parents), Q(pk__in=[]))
        )
