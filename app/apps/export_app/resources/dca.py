from import_export import fields, resources
from import_export.widgets import ForeignKeyWidget

from apps.dca.models import DCAStrategy, DCAEntry
from apps.currencies.models import Currency
from apps.export_app.widgets.numbers import UniversalDecimalWidget


class DCAStrategyResource(resources.ModelResource):
    target_currency = fields.Field(
        attribute="target_currency",
        column_name="target_currency",
        widget=ForeignKeyWidget(Currency, "name"),
    )
    payment_currency = fields.Field(
        attribute="payment_currency",
        column_name="payment_currency",
        widget=ForeignKeyWidget(Currency, "name"),
    )

    class Meta:
        model = DCAStrategy


class DCAEntryResource(resources.ModelResource):
    amount_paid = fields.Field(
        attribute="amount_paid",
        column_name="amount_paid",
        widget=UniversalDecimalWidget(),
    )
    amount_received = fields.Field(
        attribute="amount_received",
        column_name="amount_received",
        widget=UniversalDecimalWidget(),
    )

    class Meta:
        model = DCAEntry
