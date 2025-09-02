import decimal
import logging
import traceback
from copy import deepcopy
from datetime import datetime, date
from decimal import Decimal
from itertools import chain
from pprint import pformat
from random import randint, random
from textwrap import indent
from typing import Literal

from cachalot.api import cachalot_disabled
from dateutil.relativedelta import relativedelta
from django.contrib.auth import get_user_model
from django.forms import model_to_dict
from procrastinate.contrib.django import app
from simpleeval import EvalWithCompoundTypes

from apps.accounts.models import Account
from apps.common.middleware.thread_local import write_current_user, delete_current_user
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
from apps.rules.utils import transactions

logger = logging.getLogger(__name__)


class DryRunResults:
    def __init__(self):
        self.results = []

    def triggering_transaction(self, instance):
        result = {
            "type": "triggering_transaction",
            "transaction": instance,
        }
        self.results.append(result)

    def edit_transaction(
        self, instance, action, old_value, new_value, field, tags, entities
    ):
        result = {
            "type": "edit_transaction",
            "transaction": deepcopy(instance),
            "action": action,
            "old_value": old_value,
            "new_value": new_value,
            "field": field,
            "tags": tags,
            "entities": entities,
        }
        self.results.append(result)

    def update_or_create_transaction(
        self,
        updated: bool,
        action,
        query,
        tags,
        entities,
        start_instance=None,
        end_instance=None,
    ):
        result = {
            "type": "update_or_create_transaction",
            "start_transaction": start_instance,
            "end_transaction": end_instance,
            "updated": updated,
            "action": action,
            "query": query,
            "tags": tags,
            "entities": entities,
        }
        self.results.append(result)

    def error(
        self,
        action: Literal["update_or_create_transaction", "edit_transaction"],
        error,
        action_obj,
    ):
        result = {
            "type": "error",
            "action": action,
            "action_obj": action_obj,
            "error": error,
            "traceback": traceback.format_exc(),
        }
        self.results.append(result)


@app.task(name="check_for_transaction_rules")
def check_for_transaction_rules(
    instance_id=None,
    transaction_data=None,
    old_data=None,
    user_id=None,
    signal=None,
    is_hard_deleted=False,
    dry_run=False,
    rule_id=None,
):
    def _log(message: str, level="info"):
        if dry_run:
            if logs is not None:
                logs.append(message)
                if level == "error":
                    logs.append(traceback.format_exc())
        else:
            if level == "info":
                logger.info(message)
            elif level == "error":
                logger.error(message, exc_info=True)

    def _clear_names(prefix: str):
        for k in list(simple.names.keys()):
            if k.startswith(prefix):
                del simple.names[k]

    def _get_names(instance: Transaction | dict, prefix: str = ""):
        if isinstance(instance, Transaction):
            return {
                f"{prefix}id": instance.id,
                f"{prefix}account_name": instance.account.name if instance.id else None,
                f"{prefix}account_id": instance.account.id if instance.id else None,
                f"{prefix}account_group_name": (
                    instance.account.group.name
                    if instance.id and instance.account.group
                    else None
                ),
                f"{prefix}account_group_id": (
                    instance.account.group.id
                    if instance.id and instance.account.group
                    else None
                ),
                f"{prefix}is_asset_account": (
                    instance.account.is_asset if instance.id else None
                ),
                f"{prefix}is_archived_account": (
                    instance.account.is_archived if instance.id else None
                ),
                f"{prefix}category_name": (
                    instance.category.name if instance.category else None
                ),
                f"{prefix}category_id": (
                    instance.category.id if instance.category else None
                ),
                f"{prefix}tag_names": (
                    [x.name for x in instance.tags.all()] if instance.id else []
                ),
                f"{prefix}tag_ids": (
                    [x.id for x in instance.tags.all()] if instance.id else []
                ),
                f"{prefix}entities_names": (
                    [x.name for x in instance.entities.all()] if instance.id else []
                ),
                f"{prefix}entities_ids": (
                    [x.id for x in instance.entities.all()] if instance.id else []
                ),
                f"{prefix}is_expense": instance.type == Transaction.Type.EXPENSE,
                f"{prefix}is_income": instance.type == Transaction.Type.INCOME,
                f"{prefix}is_paid": instance.is_paid,
                f"{prefix}description": instance.description,
                f"{prefix}amount": instance.amount or 0,
                f"{prefix}notes": instance.notes,
                f"{prefix}date": instance.date,
                f"{prefix}reference_date": instance.reference_date,
                f"{prefix}internal_note": instance.internal_note,
                f"{prefix}internal_id": instance.internal_id,
                f"{prefix}is_deleted": instance.deleted,
                f"{prefix}is_muted": instance.mute,
            }
        else:
            return {
                f"{prefix}id": instance.get("id"),
                f"{prefix}account_name": instance.get("account", (None, None))[1],
                f"{prefix}account_id": instance.get("account", (None, None))[0],
                f"{prefix}account_group_name": instance.get(
                    "account_group", (None, None)
                )[1],
                f"{prefix}account_group_id": instance.get(
                    "account_group", (None, None)
                )[0],
                f"{prefix}is_asset_account": instance.get("is_asset"),
                f"{prefix}is_archived_account": instance.get("is_archived"),
                f"{prefix}category_name": instance.get("category", (None, None))[1],
                f"{prefix}category_id": instance.get("category", (None, None))[0],
                f"{prefix}tag_names": [x[1] for x in instance.get("tags", [])],
                f"{prefix}tag_ids": [x[0] for x in instance.get("tags", [])],
                f"{prefix}entities_names": [x[1] for x in instance.get("entities", [])],
                f"{prefix}entities_ids": [x[0] for x in instance.get("entities", [])],
                f"{prefix}is_expense": instance.get("type") == Transaction.Type.EXPENSE,
                f"{prefix}is_income": instance.get("type") == Transaction.Type.INCOME,
                f"{prefix}is_paid": instance.get("is_paid"),
                f"{prefix}description": instance.get("description", ""),
                f"{prefix}amount": Decimal(instance.get("amount")),
                f"{prefix}notes": instance.get("notes", ""),
                f"{prefix}date": datetime.fromisoformat(instance.get("date")),
                f"{prefix}reference_date": datetime.fromisoformat(
                    instance.get("reference_date")
                ),
                f"{prefix}internal_note": instance.get("internal_note", ""),
                f"{prefix}internal_id": instance.get("internal_id", ""),
                f"{prefix}is_deleted": instance.get("deleted", True),
                f"{prefix}is_muted": instance.get("mute", False),
            }

    def _process_update_or_create_transaction_action(processed_action):
        """Helper to process a single linked transaction action"""

        # Build search query using the helper method
        search_query = processed_action.build_search_query(simple)
        _log(f"   ├─ Searching transactions using: {search_query}")

        starting_instance = None

        # Find latest matching transaction or create new
        if search_query:
            transactions = Transaction.objects.filter(search_query).order_by(
                "-date", "-id"
            )
            if transactions.exists():
                transaction = transactions.first()
                existing = True
                starting_instance = deepcopy(transaction)
                _log("   ├─ Found at least one matching transaction, using latest:")
                _log(
                    "     ├─ {}".format(
                        indent(pformat(model_to_dict(transaction)), "     ")
                    )
                )
            else:
                transaction = Transaction()
                existing = False
                _log(
                    "   ├─ No matching transaction found, creating a new transaction",
                )
        else:
            transaction = Transaction()
            existing = False
            _log(
                "   ├─ No matching transaction found, creating a new transaction",
            )

        simple.names.update(_get_names(transaction, prefix="my_"))

        if processed_action.filter:
            value = simple.eval(processed_action.filter)
            if not value:
                _log(
                    "   ├─ Filter did not match. Execution of this action has been stopped."
                )
                return  # Short-circuit execution if filter evaluates to false

        # Set fields if provided
        if processed_action.set_account:
            value = simple.eval(processed_action.set_account)
            if isinstance(value, int):
                transaction.account = Account.objects.get(id=value)
            else:
                transaction.account = Account.objects.get(name=value)

        if processed_action.set_type:
            transaction.type = simple.eval(processed_action.set_type)

        if processed_action.set_is_paid:
            transaction.is_paid = simple.eval(processed_action.set_is_paid)

        if processed_action.set_mute:
            transaction.is_paid = simple.eval(processed_action.set_mute)

        if processed_action.set_date:
            transaction.date = simple.eval(processed_action.set_date)

        if processed_action.set_reference_date:
            transaction.reference_date = simple.eval(
                processed_action.set_reference_date
            )

        if processed_action.set_amount:
            transaction.amount = simple.eval(processed_action.set_amount)

        if processed_action.set_description:
            transaction.description = simple.eval(processed_action.set_description)

        if processed_action.set_internal_note:
            transaction.internal_note = simple.eval(processed_action.set_internal_note)

        if processed_action.set_internal_id:
            transaction.internal_id = simple.eval(processed_action.set_internal_id)

        if processed_action.set_notes:
            transaction.notes = simple.eval(processed_action.set_notes)

        if processed_action.set_category:
            value = simple.eval(processed_action.set_category)
            if isinstance(value, int):
                transaction.category = TransactionCategory.objects.get(id=value)
            else:
                transaction.category = TransactionCategory.objects.get(name=value)

        if dry_run:
            if not transaction.id:
                _log("   ├─ Transaction would be created as:")
            else:
                _log("   ├─ Trasanction would be updated as:")

            _log(
                "     ├─ {}".format(
                    indent(
                        pformat(
                            model_to_dict(transaction, exclude=["tags", "entities"])
                        ),
                        "     ",
                    )
                )
            )
        else:
            if not transaction.id:
                _log("   ├─ Transaction will be created as:")
            else:
                _log("   ├─ Trasanction will be updated as:")

            _log(
                "     ├─ {}".format(
                    indent(
                        pformat(
                            model_to_dict(transaction, exclude=["tags", "entities"])
                        ),
                        "     ",
                    )
                )
            )
            transaction.save()

        # Handle M2M fields after save
        tags = []
        if processed_action.set_tags:
            tags = simple.eval(processed_action.set_tags)
            if dry_run:
                _log(f"     ├─ And tags would be set as: {tags}")
            else:
                _log(f"     ├─ And tags will be set as: {tags}")
                transaction.tags.clear()
                if isinstance(tags, (list, tuple)):
                    for tag in tags:
                        if isinstance(tag, int):
                            transaction.tags.add(TransactionTag.objects.get(id=tag))
                        else:
                            transaction.tags.add(TransactionTag.objects.get(name=tag))
                elif isinstance(tags, (int, str)):
                    if isinstance(tags, int):
                        transaction.tags.add(TransactionTag.objects.get(id=tags))
                    else:
                        transaction.tags.add(TransactionTag.objects.get(name=tags))

        entities = []
        if processed_action.set_entities:
            entities = simple.eval(processed_action.set_entities)
            if dry_run:
                _log(f"     ├─ And entities would be set as: {entities}")
            else:
                _log(f"     ├─ And entities will be set as: {entities}")
                transaction.entities.clear()
                if isinstance(entities, (list, tuple)):
                    for entity in entities:
                        if isinstance(entity, int):
                            transaction.entities.add(
                                TransactionEntity.objects.get(id=entity)
                            )
                        else:
                            transaction.entities.add(
                                TransactionEntity.objects.get(name=entity)
                            )
                elif isinstance(entities, (int, str)):
                    if isinstance(entities, int):
                        transaction.entities.add(
                            TransactionEntity.objects.get(id=entities)
                        )
                    else:
                        transaction.entities.add(
                            TransactionEntity.objects.get(name=entities)
                        )

        transaction.full_clean()

        dry_run_results.update_or_create_transaction(
            start_instance=starting_instance,
            end_instance=deepcopy(transaction),
            updated=existing,
            action=processed_action,
            query=search_query,
            entities=entities,
            tags=tags,
        )

    def _process_edit_transaction_action(instance, processed_action) -> Transaction:
        field = processed_action.field
        original_value = getattr(instance, field)
        new_value = simple.eval(processed_action.value)

        tags = []
        entities = []

        _log(
            f"   ├─ Changing field '{field}' from '{original_value}' to '{new_value}'",
        )

        form_data = {}

        if field in [
            TransactionRuleAction.Field.type,
            TransactionRuleAction.Field.is_paid,
            TransactionRuleAction.Field.date,
            TransactionRuleAction.Field.reference_date,
            TransactionRuleAction.Field.amount,
            TransactionRuleAction.Field.description,
            TransactionRuleAction.Field.notes,
            TransactionRuleAction.Field.mute,
            TransactionRuleAction.Field.internal_note,
            TransactionRuleAction.Field.internal_id,
        ]:
            setattr(
                instance,
                field,
                new_value,
            )

        elif field == TransactionRuleAction.Field.account:
            if isinstance(new_value, int):
                account = Account.objects.get(id=new_value)
                instance.account = account
            elif isinstance(new_value, str):
                account = Account.objects.filter(name=new_value).first()
                instance.account = account

        elif field == TransactionRuleAction.Field.category:
            if isinstance(new_value, int):
                category = TransactionCategory.objects.get(id=new_value)
                instance.category = category
            elif isinstance(new_value, str):
                category = TransactionCategory.objects.get(name=new_value)
                instance.category = category

        elif field == TransactionRuleAction.Field.tags:
            if not dry_run:
                instance.tags.clear()
            if isinstance(new_value, list):
                for tag_value in new_value:
                    if isinstance(tag_value, int):
                        tag = TransactionTag.objects.get(id=tag_value)
                        if not dry_run:
                            instance.tags.add(tag)
                        tags.append(tag)
                    elif isinstance(tag_value, str):
                        tag = TransactionTag.objects.get(name=tag_value)
                        if not dry_run:
                            instance.tags.add(tag)
                        tags.append(tag)

            elif isinstance(new_value, (int, str)):
                if isinstance(new_value, int):
                    tag = TransactionTag.objects.get(id=new_value)
                else:
                    tag = TransactionTag.objects.get(name=new_value)

                if not dry_run:
                    instance.tags.add(tag)
                tags.append(tag)

        elif field == TransactionRuleAction.Field.entities:
            if not dry_run:
                instance.entities.clear()
            if isinstance(new_value, list):
                for entity_value in new_value:
                    if isinstance(entity_value, int):
                        entity = TransactionEntity.objects.get(id=entity_value)
                        if not dry_run:
                            instance.entities.add(entity)
                        entities.append(entity)
                    elif isinstance(entity_value, str):
                        entity = TransactionEntity.objects.get(name=entity_value)
                        if not dry_run:
                            instance.entities.add(entity)
                        entities.append(entity)

            elif isinstance(new_value, (int, str)):
                if isinstance(new_value, int):
                    entity = TransactionEntity.objects.get(id=new_value)
                else:
                    entity = TransactionEntity.objects.get(name=new_value)
                if not dry_run:
                    instance.entities.add(entity)
                entities.append(entity)

        instance.full_clean()

        dry_run_results.edit_transaction(
            instance=deepcopy(instance),
            action=processed_action,
            old_value=original_value,
            new_value=new_value,
            field=field,
            tags=tags,
            entities=entities,
        )

        return instance

    user = get_user_model().objects.get(id=user_id)
    write_current_user(user)
    logs = [] if dry_run else None
    dry_run_results = DryRunResults()

    if dry_run and not rule_id:
        raise Exception("-> Cannot dry run without a rule id")

    try:
        with cachalot_disabled():
            # For deleted transactions
            if signal == "transaction_deleted" and transaction_data:
                # Create a transaction-like object from the serialized data
                if is_hard_deleted:
                    instance = transaction_data
                else:
                    instance = Transaction.deleted_objects.get(id=instance_id)
            else:
                # Regular transaction processing for creates and updates
                instance = Transaction.objects.get(id=instance_id)

            dry_run_results.triggering_transaction(deepcopy(instance))

            functions = {
                "relativedelta": relativedelta,
                "str": str,
                "int": int,
                "float": float,
                "abs": abs,
                "randint": randint,
                "random": random,
                "decimal": decimal.Decimal,
                "datetime": datetime,
                "date": date,
                "transactions": transactions.TransactionsGetter,
            }

            _log("-> Starting rule execution...")
            _log("-> Available functions: {}".format(functions.keys()))

            names = _get_names(instance)

            simple = EvalWithCompoundTypes(names=names, functions=functions)

            if signal == "transaction_updated" and old_data:
                simple.names.update(_get_names(old_data, "old_"))

            # Select rules based on the signal type
            if signal == "transaction_created":
                rules = TransactionRule.objects.filter(
                    active=True, on_create=True
                ).order_by("id")
            elif signal == "transaction_updated":
                rules = TransactionRule.objects.filter(
                    active=True, on_update=True
                ).order_by("id")
            elif signal == "transaction_deleted":
                rules = TransactionRule.objects.filter(
                    active=True, on_delete=True
                ).order_by("id")
            else:
                rules = TransactionRule.objects.filter(active=True).order_by("id")

            if dry_run and rule_id:
                rules = rules.filter(id=rule_id)

            _log("-> Testing {} rule(s)...".format(len(rules)))

            # Process the rules as before
            for rule in rules:
                _log("Testing rule: {}".format(rule.name))
                if simple.eval(rule.trigger):
                    _log("├─ Initial trigger matched!")
                    # For deleted transactions, we want to limit what actions can be performed
                    if signal == "transaction_deleted":
                        _log(
                            "├─ Event is of type 'delete'. Only processing Update or Create actions..."
                        )
                        # Process only create/update actions, not edit actions
                        for action in rule.update_or_create_transaction_actions.all():
                            try:
                                _process_update_or_create_transaction_action(
                                    processed_action=action,
                                )
                            except Exception as e:
                                _log(
                                    f"├─ Error processing update or create transaction action {action.id} on deletion",
                                    level="error",
                                )
                    else:
                        # Normal processing for non-deleted transactions
                        edit_actions = list(rule.transaction_actions.all())
                        update_or_create_actions = list(
                            rule.update_or_create_transaction_actions.all()
                        )

                        # Check if any action has a non-zero order
                        has_custom_order = any(
                            a.order > 0 for a in edit_actions
                        ) or any(a.order > 0 for a in update_or_create_actions)

                        if has_custom_order:
                            _log(
                                "├─ One or more actions have a custom order, actions will be processed ordered by "
                                "order and creation date..."
                            )
                            # Combine and sort actions by order
                            all_actions = sorted(
                                chain(edit_actions, update_or_create_actions),
                                key=lambda a: (a.order, a.id),
                            )

                            for action in all_actions:
                                try:
                                    if isinstance(action, TransactionRuleAction):
                                        instance = _process_edit_transaction_action(
                                            instance=instance,
                                            processed_action=action,
                                        )

                                        if rule.sequenced:
                                            # Update names for next actions
                                            simple.names.update(_get_names(instance))
                                    else:
                                        _process_update_or_create_transaction_action(
                                            processed_action=action,
                                        )
                                        _clear_names("my_")
                                except Exception as e:
                                    _log(
                                        f"├─ Error processing action {action.id}",
                                        level="error",
                                    )
                            # Save at the end
                            if not dry_run and signal != "transaction_deleted":
                                instance.save()
                        else:
                            _log(
                                "├─ No actions have a custom order, actions will be processed ordered by creation "
                                "date, with Edit actions running first, then Update or Create actions..."
                            )
                            # Original behavior
                            for action in edit_actions:
                                try:
                                    instance = _process_edit_transaction_action(
                                        instance=instance,
                                        processed_action=action,
                                    )
                                    if rule.sequenced:
                                        # Update names for next actions
                                        simple.names.update(_get_names(instance))
                                except Exception as e:
                                    _log(
                                        f"├─ Error processing edit transaction action {action.id}",
                                        level="error",
                                    )

                            if rule.sequenced:
                                # Update names for next actions
                                simple.names.update(_get_names(instance))
                            if not dry_run and signal != "transaction_deleted":
                                instance.save()

                            for action in update_or_create_actions:
                                try:
                                    _process_update_or_create_transaction_action(
                                        processed_action=action,
                                    )
                                    _clear_names("my_")
                                except Exception as e:
                                    _log(
                                        f"├─ Error processing update or create transaction action {action.id}",
                                        level="error",
                                    )
                else:
                    _log("├─ Initial trigger didn't match, this rule will be skipped")
    except Exception as e:
        _log(
            "** Error while executing 'check_for_transaction_rules' task",
            level="error",
        )
        delete_current_user()
        if not dry_run:
            raise e

    delete_current_user()

    if dry_run:
        return logs, dry_run_results.results

    return None
