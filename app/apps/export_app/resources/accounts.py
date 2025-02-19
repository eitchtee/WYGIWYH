from import_export import fields, resources, widgets

from apps.accounts.models import Account
from apps.export_app.widgets.foreign_key import AutoCreateForeignKeyWidget


class AccountResource(resources.ModelResource):
    group = fields.Field(
        attribute="group",
        column_name="group",
        widget=AutoCreateForeignKeyWidget("accounts.AccountGroup", "name"),
    )
    currency = fields.Field(
        attribute="currency",
        column_name="currency",
        widget=widgets.ForeignKeyWidget("currencies.Currency", "name"),
    )
    exchange_currency = fields.Field(
        attribute="exchange_currency",
        column_name="exchange_currency",
        widget=widgets.ForeignKeyWidget("currencies.Currency", "name"),
    )

    class Meta:
        model = Account
