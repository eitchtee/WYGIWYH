from django.conf import settings
from django.dispatch import receiver

from apps.transactions.models import (
    Transaction,
    transaction_created,
    transaction_updated,
    transaction_deleted,
)
from apps.rules.tasks import check_for_transaction_rules
from apps.common.middleware.thread_local import get_current_user
from apps.rules.utils.transactions import serialize_transaction


@receiver(transaction_created)
@receiver(transaction_updated)
@receiver(transaction_deleted)
def transaction_changed_receiver(sender: Transaction, signal, **kwargs):
    old_data = kwargs.get("old_data")
    if signal is transaction_deleted:
        # Serialize transaction data for processing
        transaction_data = serialize_transaction(sender, deleted=True)

        check_for_transaction_rules.defer(
            transaction_data=transaction_data,
            user_id=get_current_user().id,
            signal="transaction_deleted",
            is_hard_deleted=kwargs.get("hard_delete", not settings.ENABLE_SOFT_DELETE),
        )
        return

    for dca_entry in sender.dca_expense_entries.all():
        dca_entry.amount_paid = sender.amount
        dca_entry.save()
    for dca_entry in sender.dca_income_entries.all():
        dca_entry.amount_received = sender.amount
        dca_entry.save()

    if signal is transaction_updated and old_data:
        old_data = serialize_transaction(old_data, deleted=False)

    check_for_transaction_rules.defer(
        instance_id=sender.id,
        user_id=get_current_user().id,
        signal=(
            "transaction_created"
            if signal is transaction_created
            else "transaction_updated"
        ),
        old_data=old_data,
    )
