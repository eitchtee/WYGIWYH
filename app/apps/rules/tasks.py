import decimal
import logging
from datetime import datetime, date

from cachalot.api import cachalot_disabled
from dateutil.relativedelta import relativedelta
from procrastinate.contrib.django import app
from simpleeval import EvalWithCompoundTypes

from apps.accounts.models import Account
from apps.rules.models import (
    TransactionRule,
    TransactionRuleAction,
)
from apps.transactions.models import (
    Transaction,
    TransactionCategory,
    TransactionTag,
    TransactionEntity,
)

logger = logging.getLogger(__name__)


@app.task(name="check_for_transaction_rules")
def check_for_transaction_rules(
    instance_id: int,
    signal,
):
    try:
        with cachalot_disabled():
            instance = Transaction.objects.get(id=instance_id)

            functions = {
                "relativedelta": relativedelta,
                "str": str,
                "int": int,
                "float": float,
                "decimal": decimal.Decimal,
                "datetime": datetime,
                "date": date,
            }

            simple = EvalWithCompoundTypes(
                names=_get_names(instance), functions=functions
            )

            if signal == "transaction_created":
                rules = TransactionRule.objects.filter(
                    active=True, on_create=True
                ).order_by("id")
            elif signal == "transaction_updated":
                rules = TransactionRule.objects.filter(
                    active=True, on_update=True
                ).order_by("id")
            else:
                rules = TransactionRule.objects.filter(active=True).order_by("id")

            for rule in rules:
                if simple.eval(rule.trigger):
                    for action in rule.transaction_actions.all():
                        try:
                            instance = _process_edit_transaction_action(
                                instance=instance, action=action, simple_eval=simple
                            )
                        except Exception as e:
                            logger.error(
                                f"Error processing edit transaction action {action.id}",
                                exc_info=True,
                            )
                        # else:
                        #     simple.names.update(_get_names(instance))
                        #     instance.save()

                    simple.names.update(_get_names(instance))
                    instance.save()

                    for action in rule.update_or_create_transaction_actions.all():
                        try:
                            _process_update_or_create_transaction_action(
                                action=action, simple_eval=simple
                            )
                        except Exception as e:
                            logger.error(
                                f"Error processing update or create transaction action {action.id}",
                                exc_info=True,
                            )

    except Exception as e:
        logger.error(
            "Error while executing 'check_for_transaction_rules' task",
            exc_info=True,
        )
        raise e


def _get_names(instance):
    return {
        "id": instance.id,
        "account_name": instance.account.name,
        "account_id": instance.account.id,
        "account_group_name": (
            instance.account.group.name if instance.account.group else None
        ),
        "account_group_id": (
            instance.account.group.id if instance.account.group else None
        ),
        "is_asset_account": instance.account.is_asset,
        "is_archived_account": instance.account.is_archived,
        "category_name": instance.category.name if instance.category else None,
        "category_id": instance.category.id if instance.category else None,
        "tag_names": [x.name for x in instance.tags.all()],
        "tag_ids": [x.id for x in instance.tags.all()],
        "entities_names": [x.name for x in instance.entities.all()],
        "entities_ids": [x.id for x in instance.entities.all()],
        "is_expense": instance.type == Transaction.Type.EXPENSE,
        "is_income": instance.type == Transaction.Type.INCOME,
        "is_paid": instance.is_paid,
        "description": instance.description,
        "amount": instance.amount,
        "notes": instance.notes,
        "date": instance.date,
        "reference_date": instance.reference_date,
        "internal_note": instance.internal_note,
        "internal_id": instance.internal_id,
    }


def _process_update_or_create_transaction_action(action, simple_eval):
    """Helper to process a single linked transaction action"""

    # Build search query using the helper method
    search_query = action.build_search_query(simple_eval)
    logger.info("Searching transactions using: %s", search_query)

    # Find latest matching transaction or create new
    if search_query:
        transactions = Transaction.objects.filter(search_query).order_by("-date", "-id")
        transaction = transactions.first()
        logger.info("Found at least one matching transaction, using latest")
    else:
        transaction = None
        logger.info("No matching transaction found, creating a new transaction")

    if not transaction:
        transaction = Transaction()

    simple_eval.names.update(
        {
            "my_account_name": (transaction.account.name if transaction.id else None),
            "my_account_id": transaction.account.id if transaction.id else None,
            "my_account_group_name": (
                transaction.account.group.name
                if transaction.id and transaction.account.group
                else None
            ),
            "my_account_group_id": (
                transaction.account.group.id
                if transaction.id and transaction.account.group
                else None
            ),
            "my_is_asset_account": (
                transaction.account.is_asset if transaction.id else None
            ),
            "my_is_archived_account": (
                transaction.account.is_archived if transaction.id else None
            ),
            "my_category_name": (
                transaction.category.name if transaction.category else None
            ),
            "my_category_id": transaction.category.id if transaction.category else None,
            "my_tag_names": (
                [x.name for x in transaction.tags.all()] if transaction.id else []
            ),
            "my_tag_ids": (
                [x.id for x in transaction.tags.all()] if transaction.id else []
            ),
            "my_entities_names": (
                [x.name for x in transaction.entities.all()] if transaction.id else []
            ),
            "my_entities_ids": (
                [x.id for x in transaction.entities.all()] if transaction.id else []
            ),
            "my_is_expense": transaction.type == Transaction.Type.EXPENSE,
            "my_is_income": transaction.type == Transaction.Type.INCOME,
            "my_is_paid": transaction.is_paid,
            "my_description": transaction.description,
            "my_amount": transaction.amount or 0,
            "my_notes": transaction.notes,
            "my_date": transaction.date,
            "my_reference_date": transaction.reference_date,
            "my_internal_note": transaction.internal_note,
            "my_internal_id": transaction.reference_date,
        }
    )

    if action.filter:
        value = simple_eval.eval(action.filter)
        if not value:
            return  # Short-circuit execution if filter evaluates to false

    # Set fields if provided
    if action.set_account:
        value = simple_eval.eval(action.set_account)
        if isinstance(value, int):
            transaction.account = Account.objects.get(id=value)
        else:
            transaction.account = Account.objects.get(name=value)

    if action.set_type:
        transaction.type = simple_eval.eval(action.set_type)

    if action.set_is_paid:
        transaction.is_paid = simple_eval.eval(action.set_is_paid)

    if action.set_date:
        transaction.date = simple_eval.eval(action.set_date)

    if action.set_reference_date:
        transaction.reference_date = simple_eval.eval(action.set_reference_date)

    if action.set_amount:
        transaction.amount = simple_eval.eval(action.set_amount)

    if action.set_description:
        transaction.description = simple_eval.eval(action.set_description)

    if action.set_internal_note:
        transaction.internal_note = simple_eval.eval(action.set_internal_note)

    if action.set_internal_id:
        transaction.internal_id = simple_eval.eval(action.set_internal_id)

    if action.set_notes:
        transaction.notes = simple_eval.eval(action.set_notes)

    if action.set_category:
        value = simple_eval.eval(action.set_category)
        if isinstance(value, int):
            transaction.category = TransactionCategory.objects.get(id=value)
        else:
            transaction.category = TransactionCategory.objects.get(name=value)

    transaction.save()

    # Handle M2M fields after save
    if action.set_tags:
        tags_value = simple_eval.eval(action.set_tags)
        transaction.tags.clear()
        if isinstance(tags_value, (list, tuple)):
            for tag in tags_value:
                if isinstance(tag, int):
                    transaction.tags.add(TransactionTag.objects.get(id=tag))
                else:
                    transaction.tags.add(TransactionTag.objects.get(name=tag))
        elif isinstance(tags_value, (int, str)):
            if isinstance(tags_value, int):
                transaction.tags.add(TransactionTag.objects.get(id=tags_value))
            else:
                transaction.tags.add(TransactionTag.objects.get(name=tags_value))

    if action.set_entities:
        entities_value = simple_eval.eval(action.set_entities)
        transaction.entities.clear()
        if isinstance(entities_value, (list, tuple)):
            for entity in entities_value:
                if isinstance(entity, int):
                    transaction.entities.add(TransactionEntity.objects.get(id=entity))
                else:
                    transaction.entities.add(TransactionEntity.objects.get(name=entity))
        elif isinstance(entities_value, (int, str)):
            if isinstance(entities_value, int):
                transaction.entities.add(
                    TransactionEntity.objects.get(id=entities_value)
                )
            else:
                transaction.entities.add(
                    TransactionEntity.objects.get(name=entities_value)
                )


def _process_edit_transaction_action(instance, action, simple_eval) -> Transaction:
    if action.field in [
        TransactionRuleAction.Field.type,
        TransactionRuleAction.Field.is_paid,
        TransactionRuleAction.Field.date,
        TransactionRuleAction.Field.reference_date,
        TransactionRuleAction.Field.amount,
        TransactionRuleAction.Field.description,
        TransactionRuleAction.Field.notes,
    ]:
        setattr(
            instance,
            action.field,
            simple_eval.eval(action.value),
        )

    elif action.field == TransactionRuleAction.Field.account:
        value = simple_eval.eval(action.value)
        if isinstance(value, int):
            account = Account.objects.get(id=value)
            instance.account = account
        elif isinstance(value, str):
            account = Account.objects.filter(name=value).first()
            instance.account = account

    elif action.field == TransactionRuleAction.Field.category:
        value = simple_eval.eval(action.value)
        if isinstance(value, int):
            category = TransactionCategory.objects.get(id=value)
            instance.category = category
        elif isinstance(value, str):
            category = TransactionCategory.objects.get(name=value)
            instance.category = category

    elif action.field == TransactionRuleAction.Field.tags:
        value = simple_eval.eval(action.value)
        if isinstance(value, list):
            # Clear existing tags
            instance.tags.clear()
            for tag_value in value:
                if isinstance(tag_value, int):
                    tag = TransactionTag.objects.get(id=tag_value)
                    instance.tags.add(tag)
                elif isinstance(tag_value, str):
                    tag = TransactionTag.objects.get(name=tag_value)
                    instance.tags.add(tag)

        elif isinstance(value, (int, str)):
            # If a single value is provided, treat it as a single tag
            instance.tags.clear()
            if isinstance(value, int):
                tag = TransactionTag.objects.get(id=value)
            else:
                tag = TransactionTag.objects.get(name=value)

            instance.tags.add(tag)

    elif action.field == TransactionRuleAction.Field.entities:
        value = simple_eval.eval(action.value)
        if isinstance(value, list):
            # Clear existing entities
            instance.entities.clear()
            for entity_value in value:
                if isinstance(entity_value, int):
                    entity = TransactionEntity.objects.get(id=entity_value)
                    instance.entities.add(entity)
                elif isinstance(entity_value, str):
                    entity = TransactionEntity.objects.get(name=entity_value)
                    instance.entities.add(entity)

        elif isinstance(value, (int, str)):
            # If a single value is provided, treat it as a single entity
            instance.entities.clear()
            if isinstance(value, int):
                entity = TransactionEntity.objects.get(id=value)
            else:
                entity = TransactionEntity.objects.get(name=value)

            instance.entities.add(entity)

    return instance
