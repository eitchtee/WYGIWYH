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
    for dca_entry in sender.dca_expense_entries.all():
        dca_entry.amount_paid = sender.amount
        dca_entry.save()
    for dca_entry in sender.dca_income_entries.all():
        dca_entry.amount_received = sender.amount
        dca_entry.save()

    check_for_transaction_rules.defer(
        instance_id=sender.id,
        signal=(
            "transaction_created"
            if signal is transaction_created
            else "transaction_updated"
        ),
    )
