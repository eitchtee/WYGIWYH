from django.dispatch import receiver

from apps.transactions.models import (
    Transaction,
    transaction_created,
    transaction_updated,
)
from apps.rules.tasks import check_for_transaction_rules


@receiver(transaction_created)
@receiver(transaction_updated)
def transaction_changed_receiver(sender: Transaction, signal, **kwargs):
    check_for_transaction_rules.defer(
        instance_id=sender.id,
        signal=(
            "transaction_created"
            if signal is transaction_created
            else "transaction_updated"
        ),
    )
