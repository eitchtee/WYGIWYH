from import_export import fields, resources, widgets

from apps.accounts.models import Account, AccountGroup
from apps.export_app.widgets.foreign_key import AutoCreateForeignKeyWidget
from apps.currencies.models import Currency


class AccountResource(resources.ModelResource):
    group = fields.Field(
        attribute="group",
        column_name="group",
        widget=AutoCreateForeignKeyWidget(AccountGroup, "name"),
    )
    currency = fields.Field(
        attribute="currency",
        column_name="currency",
        widget=widgets.ForeignKeyWidget(Currency, "name"),
    )
    exchange_currency = fields.Field(
        attribute="exchange_currency",
        column_name="exchange_currency",
        widget=widgets.ForeignKeyWidget(Currency, "name"),
    )

    class Meta:
        model = Account

    def get_queryset(self):
        return Account.all_objects.all()
