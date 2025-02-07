import logging
from datetime import timedelta

from cachalot.api import cachalot_disabled, invalidate
from django.utils import timezone
from django.conf import settings

from procrastinate.contrib.django import app

from apps.transactions.models import RecurringTransaction, Transaction

logger = logging.getLogger(__name__)


@app.periodic(cron="0 0 * * *")
@app.task(name="generate_recurring_transactions")
def generate_recurring_transactions(timestamp=None):
    try:
        RecurringTransaction.generate_upcoming_transactions()
    except Exception as e:
        logger.error(
            "Error while executing 'generate_recurring_transactions' task",
            exc_info=True,
        )
        raise e


@app.periodic(cron="10 1 * * *")
@app.task(name="cleanup_deleted_transactions")
def cleanup_deleted_transactions(timestamp=None):
    with cachalot_disabled():
        if settings.ENABLE_SOFT_DELETE and settings.KEEP_DELETED_TRANSACTIONS_FOR == 0:
            return "KEEP_DELETED_TRANSACTIONS_FOR is 0, no cleanup performed."

        if not settings.ENABLE_SOFT_DELETE:
            # Hard delete all soft-deleted transactions
            deleted_count, _ = Transaction.deleted_objects.all().hard_delete()
            return (
                f"Hard deleted {deleted_count} transactions (soft deletion disabled)."
            )

        # Calculate the cutoff date
        cutoff_date = timezone.now() - timedelta(
            days=settings.KEEP_DELETED_TRANSACTIONS_FOR
        )

    invalidate()

    # Hard delete soft-deleted transactions older than the cutoff date
    old_transactions = Transaction.deleted_objects.filter(deleted_at__lt=cutoff_date)
    deleted_count, _ = old_transactions.hard_delete()

    return f"Hard deleted {deleted_count} objects older than {settings.KEEP_DELETED_TRANSACTIONS_FOR} days."
