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


@receiver(transaction_created)
@receiver(transaction_updated)
@receiver(transaction_deleted)
def transaction_changed_receiver(sender: Transaction, signal, **kwargs):
    if signal is transaction_deleted:
        # Serialize transaction data for processing
        transaction_data = {
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
            "deleted": True,
            "internal_note": sender.internal_note,
            "internal_id": sender.internal_id,
        }

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

    check_for_transaction_rules.defer(
        instance_id=sender.id,
        user_id=get_current_user().id,
        signal=(
            "transaction_created"
            if signal is transaction_created
            else "transaction_updated"
        ),
    )
