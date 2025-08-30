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
