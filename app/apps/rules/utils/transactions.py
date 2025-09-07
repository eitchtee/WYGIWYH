import logging
from decimal import Decimal

from django.db.models import Sum, Value, DecimalField, Case, When, F
from django.db.models.functions import Coalesce

from apps.transactions.models import (
    Transaction,
)

logger = logging.getLogger(__name__)


class TransactionsGetter:
    def __init__(self, **filters):
        self.__queryset = Transaction.objects.filter(**filters)

    def exclude(self, **exclude_filters):
        self.__queryset = Transaction.objects.exclude(**exclude_filters)

    @property
    def sum(self):
        return self.__queryset.aggregate(
            total=Coalesce(
                Sum("amount"), Value(Decimal("0")), output_field=DecimalField()
            )
        )["total"]

    @property
    def balance(self):
        return abs(
            self.__queryset.aggregate(
                balance=Coalesce(
                    Sum(
                        Case(
                            When(type=Transaction.Type.EXPENSE, then=-F("amount")),
                            default=F("amount"),
                            output_field=DecimalField(),
                        )
                    ),
                    Value(Decimal("0")),
                    output_field=DecimalField(),
                )
            )["balance"]
        )

    @property
    def raw_balance(self):
        return self.__queryset.aggregate(
            balance=Coalesce(
                Sum(
                    Case(
                        When(type=Transaction.Type.EXPENSE, then=-F("amount")),
                        default=F("amount"),
                        output_field=DecimalField(),
                    )
                ),
                Value(Decimal("0")),
                output_field=DecimalField(),
            )
        )["balance"]


def serialize_transaction(sender: Transaction, deleted: bool):
    return {
        "id": sender.id,
        "account": (sender.account.id, sender.account.name),
        "account_group": (
            sender.account.group.id if sender.account.group else None,
            sender.account.group.name if sender.account.group else None,
        ),
        "type": str(sender.type),
        "is_paid": sender.is_paid,
        "is_asset": sender.account.is_asset,
        "is_archived": sender.account.is_archived,
        "category": (
            sender.category.id if sender.category else None,
            sender.category.name if sender.category else None,
        ),
        "date": sender.date.isoformat(),
        "reference_date": sender.reference_date.isoformat(),
        "amount": str(sender.amount),
        "description": sender.description,
        "notes": sender.notes,
        "tags": list(sender.tags.values_list("id", "name")),
        "entities": list(sender.entities.values_list("id", "name")),
        "deleted": deleted,
        "internal_note": sender.internal_note,
        "internal_id": sender.internal_id,
        "mute": sender.mute,
    }
