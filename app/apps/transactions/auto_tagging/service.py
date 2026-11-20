from __future__ import annotations

import logging
from collections import OrderedDict, defaultdict
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from apps.common.middleware.thread_local import (
    delete_current_user,
    get_current_user,
    write_current_user,
)
from apps.transactions.auto_tagging.classifier import (
    MAX_TRAINING_DOCS,
    MODEL_VERSION,
    Prediction,
    TrainingRecord,
    TransactionAutoTagger,
)
from apps.transactions.models import (
    AutoTaggerModel,
    Transaction,
    TransactionCategory,
    TransactionEntity,
    TransactionTag,
)

logger = logging.getLogger(__name__)

STALE_MODEL_AGE = timedelta(hours=1)
_TAGGER_CACHE_MAXSIZE = 4
_tagger_cache: OrderedDict[tuple[int, str, int], TransactionAutoTagger] = OrderedDict()


def _get_cached_tagger(model_obj: AutoTaggerModel) -> TransactionAutoTagger | None:
    cache_key = (model_obj.user_id, model_obj.trained_at.isoformat(), model_obj.version)
    cached = _tagger_cache.get(cache_key)
    if cached is not None:
        _tagger_cache.move_to_end(cache_key)
        return cached

    tagger = TransactionAutoTagger.from_bytes(model_obj.data)
    if tagger is not None:
        _tagger_cache[cache_key] = tagger
        while len(_tagger_cache) > _TAGGER_CACHE_MAXSIZE:
            _tagger_cache.popitem(last=False)
    return tagger


def _with_user_context(user):
    """Context manager that temporarily sets the thread-local current user."""

    class _UserContext:
        def __init__(self, target_user):
            self.target_user = target_user
            self.previous_user = None

        def __enter__(self):
            self.previous_user = get_current_user()
            write_current_user(self.target_user)
            return self.target_user

        def __exit__(self, exc_type, exc_val, exc_tb):
            if self.previous_user is not None:
                write_current_user(self.previous_user)
            elif get_current_user() is not None:
                delete_current_user()

    return _UserContext(user)


def train_for_user(user) -> AutoTaggerModel:
    """Train and persist the auto-tagging model for a single user."""
    with _with_user_context(user):
        qs = (
            Transaction.objects.filter(linked_transaction__isnull=True)
            .exclude(Q(description="") & Q(notes=""))
            .filter(
                Q(category__isnull=False)
                | Q(tags__isnull=False)
                | Q(entities__isnull=False)
            )
            .distinct()
            .order_by("-date", "-id")
            .values_list(
                "id",
                "description",
                "notes",
                "account_id",
                "type",
                "amount",
                "category_id",
            )[:MAX_TRAINING_DOCS]
        )
        rows = list(qs)

        tx_ids = [row[0] for row in rows]
        tags_by_tx: dict[int, list[int]] = defaultdict(list)
        entities_by_tx: dict[int, list[int]] = defaultdict(list)

        if tx_ids:
            for tx_id, tag_id in Transaction.tags.through.objects.filter(
                transaction_id__in=tx_ids
            ).values_list("transaction_id", "transactiontag_id"):
                tags_by_tx[tx_id].append(tag_id)

            for tx_id, entity_id in Transaction.entities.through.objects.filter(
                transaction_id__in=tx_ids
            ).values_list("transaction_id", "transactionentity_id"):
                entities_by_tx[tx_id].append(entity_id)

    records = [
        TrainingRecord(
            description=description or "",
            notes=notes or "",
            account_id=account_id,
            tx_type=tx_type,
            amount=amount,
            category_id=category_id,
            tag_ids=tuple(tags_by_tx.get(tx_id, ())),
            entity_ids=tuple(entities_by_tx.get(tx_id, ())),
        )
        for tx_id, description, notes, account_id, tx_type, amount, category_id in rows
    ]

    tagger = TransactionAutoTagger.fit(records)
    model_obj, _ = AutoTaggerModel.objects.update_or_create(
        user=user,
        defaults={
            "data": tagger.to_bytes(),
            "transaction_count": tagger.num_docs,
            "version": MODEL_VERSION,
        },
    )
    return model_obj


def ensure_model_fresh_async(user_id: int) -> None:
    """Defer a background retrain if Procrastinate is available."""
    from apps.transactions.tasks import train_user_auto_tagger

    try:
        train_user_auto_tagger.configure(
            queueing_lock=f"train_auto_tagger_{user_id}"
        ).defer(user_id=user_id)
    except Exception:
        logger.debug(
            "Could not defer auto-tagger training for user %s",
            user_id,
            exc_info=True,
        )


def _load_or_train_tagger(user) -> TransactionAutoTagger | None:
    model_obj = AutoTaggerModel.objects.filter(user=user).first()
    if model_obj is None or model_obj.version != MODEL_VERSION:
        model_obj = train_for_user(user)
    elif timezone.now() - model_obj.trained_at > STALE_MODEL_AGE:
        ensure_model_fresh_async(user.id)

    return _get_cached_tagger(model_obj)


def apply_auto_tagging(instance: Transaction, user) -> bool:
    """Auto-assign category, tags, and entities to an unclassified transaction.

    Only runs when:
    - The user has auto_tagging enabled in UserSettings
    - The transaction is not deleted and not part of a transfer
    - The transaction currently has NO category, NO tags, and NO entities
    """
    user_settings = getattr(user, "settings", None)
    if user_settings is None or not user_settings.auto_tagging:
        return False

    if instance.deleted or instance.linked_transaction_id is not None:
        return False

    if (
        instance.category_id is not None
        or Transaction.tags.through.objects.filter(transaction_id=instance.pk).exists()
        or Transaction.entities.through.objects.filter(
            transaction_id=instance.pk
        ).exists()
    ):
        return False

    with _with_user_context(user):
        tagger = _load_or_train_tagger(user)
        if tagger is None or tagger.num_docs == 0:
            return False

        allowed_category_ids = set(
            TransactionCategory.objects.filter(
                active=True, auto_match=True
            ).values_list("id", flat=True)
        )
        allowed_tag_ids = set(
            TransactionTag.objects.filter(
                active=True, auto_match=True
            ).values_list("id", flat=True)
        )
        allowed_entity_ids = set(
            TransactionEntity.objects.filter(
                active=True, auto_match=True
            ).values_list("id", flat=True)
        )

        prediction: Prediction = tagger.predict(
            description=instance.description,
            notes=instance.notes,
            account_id=instance.account_id,
            tx_type=instance.type,
            amount=instance.amount,
            allowed_category_ids=allowed_category_ids,
            allowed_tag_ids=allowed_tag_ids,
            allowed_entity_ids=allowed_entity_ids,
        )

        if prediction.is_empty:
            return False

        if prediction.category_id is not None:
            Transaction.all_objects.filter(pk=instance.pk).update(
                emit_signal=False,
                category_id=prediction.category_id,
            )
            instance.category_id = prediction.category_id

        if prediction.tag_ids:
            instance.tags.add(*prediction.tag_ids)

        if prediction.entity_ids:
            instance.entities.add(*prediction.entity_ids)

        return True
