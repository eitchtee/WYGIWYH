from import_export import fields, resources

from apps.export_app.widgets.foreign_key import AutoCreateForeignKeyWidget
from apps.export_app.widgets.many_to_many import AutoCreateManyToManyWidget
from apps.transactions.models import (
    Transaction,
    TransactionCategory,
    TransactionTag,
    TransactionEntity,
)


class TransactionResource(resources.ModelResource):
    account = fields.Field(
        attribute="account",
        column_name="account",
        widget=AutoCreateForeignKeyWidget("accounts.Account", "name"),
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

    class Meta:
        model = Transaction
