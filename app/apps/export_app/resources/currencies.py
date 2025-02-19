from import_export import fields, resources, widgets

from apps.accounts.models import Account
from apps.currencies.models import Currency, ExchangeRate, ExchangeRateService
from apps.export_app.widgets.foreign_key import SkipMissingForeignKeyWidget
from apps.export_app.widgets.numbers import UniversalDecimalWidget


class CurrencyResource(resources.ModelResource):
    exchange_currency = fields.Field(
        attribute="exchange_currency",
        column_name="exchange_currency",
        widget=SkipMissingForeignKeyWidget(Currency, "name"),
    )

    class Meta:
        model = Currency


class ExchangeRateResource(resources.ModelResource):
    from_currency = fields.Field(
        attribute="from_currency",
        column_name="from_currency",
        widget=widgets.ForeignKeyWidget(Currency, "name"),
    )
    to_currency = fields.Field(
        attribute="to_currency",
        column_name="to_currency",
        widget=widgets.ForeignKeyWidget(Currency, "name"),
    )
    rate = fields.Field(
        attribute="rate", column_name="rate", widget=UniversalDecimalWidget()
    )

    class Meta:
        model = ExchangeRate


class ExchangeRateServiceResource(resources.ModelResource):
    target_currencies = fields.Field(
        attribute="target_currencies",
        column_name="target_currencies",
        widget=widgets.ManyToManyWidget(Currency, field="name"),
    )
    target_accounts = fields.Field(
        attribute="target_accounts",
        column_name="target_accounts",
        widget=widgets.ManyToManyWidget(Account, field="name"),
    )

    class Meta:
        model = ExchangeRateService
