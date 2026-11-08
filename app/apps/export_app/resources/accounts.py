from import_export import fields, resources, widgets

from apps.accounts.models import Account, AccountGroup, InvestmentClass
from apps.export_app.widgets.foreign_key import AutoCreateForeignKeyWidget
from apps.currencies.models import Currency


class InvestmentClassResource(resources.ModelResource):
    class Meta:
        model = InvestmentClass

    def get_queryset(self):
        return InvestmentClass.all_objects.all()


class AllClassesWidget(widgets.ForeignKeyWidget):
    # By id, across owners: a shared account may carry another user's class
    def get_queryset(self, value, row, *args, **kwargs):
        return InvestmentClass.all_objects.all()


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

    investment_class = fields.Field(
        attribute="investment_class",
        column_name="investment_class",
        widget=AllClassesWidget(InvestmentClass),
    )

    class Meta:
        model = Account

    def get_queryset(self):
        return Account.all_objects.all()
