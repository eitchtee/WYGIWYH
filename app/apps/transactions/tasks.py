import logging
from datetime import timedelta

from cachalot.api import cachalot_disabled, invalidate
from django.contrib.auth import get_user_model
from django.db.models import Max
from django.utils import timezone
from django.conf import settings

from procrastinate.contrib.django import app

from apps.transactions.auto_tagging.service import _with_user_context, train_for_user
from apps.transactions.models import AutoTaggerModel, RecurringTransaction, Transaction

logger = logging.getLogger(__name__)


@app.periodic(cron="0 0 * * *")
@app.task(
    lock="generate_recurring_transactions", name="generate_recurring_transactions"
)
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
@app.task(lock="cleanup_deleted_transactions", name="cleanup_deleted_transactions")
def cleanup_deleted_transactions(timestamp=None):
    if settings.ENABLE_SOFT_DELETE and settings.KEEP_DELETED_TRANSACTIONS_FOR == 0:
        return "KEEP_DELETED_TRANSACTIONS_FOR is 0, no cleanup performed."

    if not settings.ENABLE_SOFT_DELETE:
        # Hard delete all soft-deleted transactions
        deleted_count, _ = Transaction.userless_deleted_objects.all().hard_delete()
        return f"Hard deleted {deleted_count} transactions (soft deletion disabled)."

    # Calculate the cutoff date
    cutoff_date = timezone.now() - timedelta(
        days=settings.KEEP_DELETED_TRANSACTIONS_FOR
    )

    # Hard delete soft-deleted transactions older than the cutoff date
    old_transactions = Transaction.userless_deleted_objects.filter(
        deleted_at__lt=cutoff_date
    )
    deleted_count, _ = old_transactions.hard_delete()

    return f"Hard deleted {deleted_count} objects older than {settings.KEEP_DELETED_TRANSACTIONS_FOR} days."


@app.task(name="train_user_auto_tagger")
def train_user_auto_tagger(user_id: int):
    user = get_user_model().objects.filter(id=user_id).first()
    if user is None:
        return "User not found."

    user_settings = getattr(user, "settings", None)
    if user_settings is None or not user_settings.auto_tagging:
        return "Auto-tagging disabled for user."

    with cachalot_disabled():
        model_obj = train_for_user(user)
    return f"Trained auto-tagger for user {user_id} on {model_obj.transaction_count} transactions."


@app.periodic(cron="30 2 * * *")
@app.task(lock="retrain_auto_taggers", name="retrain_auto_taggers")
def retrain_auto_taggers(timestamp=None):
    User = get_user_model()
    users = User.objects.filter(settings__auto_tagging=True, is_active=True).select_related(
        "settings"
    )
    existing_models = {
        m.user_id: m.trained_at
        for m in AutoTaggerModel.objects.filter(user__in=users)
    }

    retrained = 0
    with cachalot_disabled():
        for user in users:
            trained_at = existing_models.get(user.id)
            with _with_user_context(user):
                latest_tx = Transaction.objects.aggregate(latest=Max("updated_at"))[
                    "latest"
                ]
            if trained_at is not None and (
                latest_tx is None or latest_tx <= trained_at
            ):
                continue
            train_for_user(user)
            retrained += 1

    return f"Retrained auto-tagger for {retrained} user(s)."
