from django.db import transaction as db_transaction

from apps.splits.auth import SplitActor
from apps.splits.models import SplitTransactionLink


@db_transaction.atomic
def leave_event(actor: SplitActor):
    """A non-organizer WYGIWYH user leaves: removed if they have no history, else deactivated."""
    # Their own links only; the linked transactions stay in their accounts
    SplitTransactionLink.objects.filter(event=actor.event, user=actor.user).delete()
    participant = actor.participant
    if participant.can_be_deleted():
        participant.delete()
    else:
        # Keep their expenses and payments so everyone else's balances stay right
        participant.is_active = False
        participant.save(update_fields=["is_active"])
