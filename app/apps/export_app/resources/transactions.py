from import_export import fields, resources

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
)
from apps.export_app.widgets.numbers import UniversalDecimalWidget


class TransactionResource(resources.ModelResource):
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
        return Transaction.userless_all_objects.all()


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


class RecurringTransactionResource(resources.ModelResource):
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

    class Meta:
        model = RecurringTransaction

    def get_queryset(self):
        return RecurringTransaction.all_objects.all()

    def dehydrate_account_owner(self, obj):
        """Export the account's owner ID for proper import matching."""
        return obj.account.owner_id if obj.account else None


class InstallmentPlanResource(resources.ModelResource):
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

    class Meta:
        model = InstallmentPlan

    def get_queryset(self):
        return InstallmentPlan.all_objects.all()

    def dehydrate_account_owner(self, obj):
        """Export the account's owner ID for proper import matching."""
        return obj.account.owner_id if obj.account else None
