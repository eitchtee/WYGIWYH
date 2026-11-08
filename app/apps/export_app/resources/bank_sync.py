from import_export import fields, resources, widgets

from apps.accounts.models import Account
from apps.bank_sync.models import BankSyncAccount, BankSyncService


class _AnyOwnerWidget(widgets.ForeignKeyWidget):
    """By id, across every user.

    The default managers only see the restoring user's rows, and names can clash
    between users. Ids survive a restore.
    """

    def get_queryset(self, value, row, *args, **kwargs):
        return self.model._base_manager.all()


class BankSyncServiceResource(resources.ModelResource):
    class Meta:
        model = BankSyncService

    def get_queryset(self):
        return BankSyncService._base_manager.all()


class BankSyncAccountResource(resources.ModelResource):
    service = fields.Field(
        attribute="service",
        column_name="service",
        widget=_AnyOwnerWidget(BankSyncService),
    )
    account = fields.Field(
        attribute="account",
        column_name="account",
        widget=_AnyOwnerWidget(Account),
    )

    class Meta:
        model = BankSyncAccount
