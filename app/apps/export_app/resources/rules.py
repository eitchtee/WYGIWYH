from import_export import fields, resources
from import_export.widgets import ForeignKeyWidget

from apps.export_app.widgets.foreign_key import AutoCreateForeignKeyWidget
from apps.export_app.widgets.many_to_many import AutoCreateManyToManyWidget
from apps.rules.models import (
    TransactionRule,
    TransactionRuleAction,
    UpdateOrCreateTransactionRuleAction,
)


class TransactionRuleResource(resources.ModelResource):
    class Meta:
        model = TransactionRule


class TransactionRuleActionResource(resources.ModelResource):
    class Meta:
        model = TransactionRuleAction


class UpdateOrCreateTransactionRuleResource(resources.ModelResource):
    class Meta:
        model = UpdateOrCreateTransactionRuleAction
