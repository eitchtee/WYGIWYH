import decimal
import logging
import sys
import traceback
from copy import deepcopy
from datetime import datetime, date
from decimal import Decimal
from itertools import chain
from pprint import pformat
from random import randint, random
from time import monotonic
from typing import Literal

from cachalot.api import cachalot_disabled
from dateutil.relativedelta import relativedelta
from django.contrib.auth import get_user_model
from django.db import transaction as db_transaction
from django.forms import model_to_dict
from django.utils import timezone
from procrastinate.contrib.django import app
from simpleeval import EvalWithCompoundTypes

from apps.accounts.models import Account
from apps.common.functions.decimals import truncate_decimal
from apps.common.middleware.thread_local import write_current_user, delete_current_user
from apps.rules.models import (
    RuleRun,
    TransactionRule,
    TransactionRuleAction,
)
from apps.transactions.auto_tagging.service import apply_auto_tagging
from apps.transactions.models import (
    SubTransaction,
    Transaction,
    TransactionCategory,
    TransactionTag,
    TransactionEntity,
)
from apps.rules.utils import transactions

logger = logging.getLogger(__name__)

SUB_TRANSACTIONS_SHAPE = (
    "Sub-transactions must be a list like [{'name': 'Fee', 'amount': 1.5}, ...]"
)


def build_sub_transactions(transaction: Transaction, value) -> list[SubTransaction]:
    """Validated sub-transactions for `transaction` from a rule expression's result."""
    if not isinstance(value, (list, tuple)):
        raise ValueError(SUB_TRANSACTIONS_SHAPE)
    places = transaction.account.currency.decimal_places
    subs = []
    for item in value:
        if not isinstance(item, dict) or item.get("amount") is None:
            raise ValueError(SUB_TRANSACTIONS_SHAPE)
        sub = SubTransaction(
            transaction=transaction,
            name=str(item.get("name") or "").strip(),
            amount=truncate_decimal(
                value=Decimal(str(item["amount"])), decimal_places=places
            ),
        )
        # the transaction may not be saved yet, so its link isn't checked here
        sub.full_clean(exclude=["transaction"], validate_constraints=False)
        subs.append(sub)
    return subs


def _snapshot(transaction: Transaction) -> Transaction:
    """A copy to show in dry-run results, as the transaction is right now."""
    copy = transaction.deepcopy()
    copy.copy_sub_transactions_from(transaction)
    return copy


class DryRunResults:
    def __init__(self, dry_run: bool):
        self.results = []
        self.dry_run = dry_run

    def header(self, header: str, action):
        if not self.dry_run:
            return

        result = {"type": "header", "header_type": header, "action": action}
        self.results.append(result)

    def triggering_transaction(self, instance):
        if not self.dry_run:
            return
        if isinstance(instance, Transaction):
            instance = _snapshot(instance)
        elif isinstance(instance, dict):
            instance = deepcopy(instance)

        result = {
            "type": "triggering_transaction",
            "transaction": instance,
        }
        self.results.append(result)

    def edit_transaction(
        self, instance, action, old_value, new_value, field, tags, entities
    ):
        if not self.dry_run:
            return
        if isinstance(instance, Transaction):
            instance = _snapshot(instance)
        elif isinstance(instance, dict):
            instance = deepcopy(instance)

        result = {
            "type": "edit_transaction",
            "transaction": instance,
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
        if not self.dry_run:
            return

        if isinstance(end_instance, Transaction):
            end_instance = _snapshot(end_instance)
        elif isinstance(end_instance, dict):
            end_instance = deepcopy(end_instance)

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

    def error(self, error, level: Literal["error", "warning", "info"] = "error"):
        if not self.dry_run:
            return

        result = {
            "type": "error",
            "error": error,
            "traceback": traceback.format_exc(),
            "level": level,
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
    rule_ids=None,
):
    # Kept so a manual run knows whether a rule applied cleanly, and why not
    errors = []

    def _log(message: str, level="info"):
        if level == "error":
            errors.append(str(sys.exc_info()[1] or message))

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

    def _get_names(transaction: Transaction | dict, prefix: str = ""):
        if isinstance(transaction, Transaction):
            return {
                "is_on_create": True if signal == "transaction_created" else False,
                "is_on_delete": True if signal == "transaction_deleted" else False,
                "is_on_update": True if signal == "transaction_updated" else False,
                f"{prefix}id": transaction.id,
                f"{prefix}account_name": (
                    transaction.account.name if transaction.id else None
                ),
                f"{prefix}account_id": (
                    transaction.account.id if transaction.id else None
                ),
                f"{prefix}account_group_name": (
                    transaction.account.group.name
                    if transaction.id and transaction.account.group
                    else None
                ),
                f"{prefix}account_group_id": (
                    transaction.account.group.id
                    if transaction.id and transaction.account.group
                    else None
                ),
                f"{prefix}is_asset_account": (
                    transaction.account.is_asset if transaction.id else None
                ),
                f"{prefix}is_archived_account": (
                    transaction.account.is_archived if transaction.id else None
                ),
                f"{prefix}category_name": (
                    transaction.category.name if transaction.category else None
                ),
                f"{prefix}category_id": (
                    transaction.category.id if transaction.category else None
                ),
                f"{prefix}tag_names": (
                    [x.name for x in transaction.tags.all()] if transaction.id else []
                ),
                f"{prefix}tag_ids": (
                    [x.id for x in transaction.tags.all()] if transaction.id else []
                ),
                f"{prefix}entities_names": (
                    [x.name for x in transaction.entities.all()]
                    if transaction.id
                    else []
                ),
                f"{prefix}entities_ids": (
                    [x.id for x in transaction.entities.all()] if transaction.id else []
                ),
                f"{prefix}sub_transactions": (
                    [
                        {"name": s.name, "amount": s.amount}
                        for s in transaction.sub_transactions.all()
                    ]
                    if transaction.id
                    else []
                ),
                f"{prefix}is_expense": transaction.type == Transaction.Type.EXPENSE,
                f"{prefix}is_income": transaction.type == Transaction.Type.INCOME,
                f"{prefix}is_paid": transaction.is_paid,
                f"{prefix}description": transaction.description,
                f"{prefix}amount": transaction.amount or 0,
                f"{prefix}notes": transaction.notes,
                f"{prefix}date": transaction.date,
                f"{prefix}reference_date": transaction.reference_date,
                f"{prefix}internal_note": transaction.internal_note,
                f"{prefix}internal_id": transaction.internal_id,
                f"{prefix}is_deleted": transaction.deleted,
                f"{prefix}is_muted": transaction.mute,
                f"{prefix}is_recurring": transaction.recurring_transaction is not None,
                f"{prefix}is_installment": transaction.installment_plan is not None,
                f"{prefix}installment_number": (
                    transaction.installment_id if transaction.installment_plan else None
                ),
                f"{prefix}installment_total": (
                    transaction.installment_plan.number_of_installments
                    if transaction.installment_plan
                    else None
                ),
            }
        else:
            return {
                "is_on_create": True if signal == "transaction_created" else False,
                "is_on_delete": True if signal == "transaction_deleted" else False,
                "is_on_update": True if signal == "transaction_updated" else False,
                f"{prefix}id": transaction.get("id"),
                f"{prefix}account_name": transaction.get("account", (None, None))[1],
                f"{prefix}account_id": transaction.get("account", (None, None))[0],
                f"{prefix}account_group_name": transaction.get(
                    "account_group", (None, None)
                )[1],
                f"{prefix}account_group_id": transaction.get(
                    "account_group", (None, None)
                )[0],
                f"{prefix}is_asset_account": transaction.get("is_asset"),
                f"{prefix}is_archived_account": transaction.get("is_archived"),
                f"{prefix}category_name": transaction.get("category", (None, None))[1],
                f"{prefix}category_id": transaction.get("category", (None, None))[0],
                f"{prefix}tag_names": [x[1] for x in transaction.get("tags", [])],
                f"{prefix}tag_ids": [x[0] for x in transaction.get("tags", [])],
                f"{prefix}entities_names": [
                    x[1] for x in transaction.get("entities", [])
                ],
                f"{prefix}entities_ids": [
                    x[0] for x in transaction.get("entities", [])
                ],
                f"{prefix}sub_transactions": [
                    {"name": s["name"], "amount": Decimal(s["amount"])}
                    for s in transaction.get("sub_transactions", [])
                ],
                f"{prefix}is_expense": transaction.get("type")
                == Transaction.Type.EXPENSE,
                f"{prefix}is_income": transaction.get("type")
                == Transaction.Type.INCOME,
                f"{prefix}is_paid": transaction.get("is_paid"),
                f"{prefix}description": transaction.get("description", ""),
                f"{prefix}amount": Decimal(transaction.get("amount")),
                f"{prefix}notes": transaction.get("notes", ""),
                f"{prefix}date": datetime.fromisoformat(transaction.get("date")),
                f"{prefix}reference_date": datetime.fromisoformat(
                    transaction.get("reference_date")
                ),
                f"{prefix}internal_note": transaction.get("internal_note", ""),
                f"{prefix}internal_id": transaction.get("internal_id", ""),
                f"{prefix}is_deleted": transaction.get("deleted", True),
                f"{prefix}is_muted": transaction.get("mute", False),
                f"{prefix}is_recurring": transaction.get(
                    "recurring_transaction", False
                ),
                f"{prefix}is_installment": transaction.get("installment", False),
                f"{prefix}installment_number": transaction.get("installment_id"),
                f"{prefix}installment_total": transaction.get("installment_total"),
            }

    def _evaluate_sub_transactions(transaction, value):
        """The parts an expression's `value` gives `transaction`, with its amount set
        to their sum, or None for a transfer, which can't have any."""
        if transaction.linked_transaction_id:
            _log("Skipped: transfers can't have sub-transactions")
            return None
        subs = build_sub_transactions(transaction, value)
        if subs:
            transaction.amount = sum(s.amount for s in subs)
        _log(f"Sub-transactions will be set as: {[(s.name, s.amount) for s in subs]}")
        return subs

    def _save_sub_transactions(transaction, subs):
        transaction.sub_transactions.all().delete()
        SubTransaction.objects.bulk_create(subs)

    def _process_update_or_create_transaction_action(processed_action):
        """Helper to process a single linked transaction action"""

        dry_run_results.header("update_or_create_transaction", action=processed_action)

        # Build search query using the helper method
        search_query = processed_action.build_search_query(simple)
        _log(f"Searching transactions using: {search_query}")

        starting_instance = None

        # Find latest matching transaction or create new
        if search_query:
            searched_transactions = Transaction.objects.filter(search_query).order_by(
                "-date", "-id"
            )
            if searched_transactions.exists():
                transaction = searched_transactions.first()
                existing = True

                if dry_run:
                    starting_instance = _snapshot(transaction)

                _log("Found at least one matching transaction, using latest:")
                _log("{}".format(pformat(model_to_dict(transaction))))
            else:
                transaction = Transaction()
                existing = False
                _log(
                    "No matching transaction found, creating a new transaction",
                )
        else:
            transaction = Transaction()
            existing = False
            _log(
                "No matching transaction found, creating a new transaction",
            )

        simple.names.update(_get_names(transaction, prefix="my_"))

        if processed_action.filter:
            value = simple.eval(processed_action.filter)
            if not value:
                dry_run_results.error(
                    error="Filter did not match. Execution of this action has stopped.",
                )
                _log("Filter did not match. Execution of this action has stopped.")
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
            transaction.mute = simple.eval(processed_action.set_mute)

        if processed_action.set_date:
            transaction.date = simple.eval(processed_action.set_date)

        if processed_action.set_reference_date:
            transaction.reference_date = simple.eval(
                processed_action.set_reference_date
            )

        subs = None
        if processed_action.set_sub_transactions:
            subs = _evaluate_sub_transactions(
                transaction, simple.eval(processed_action.set_sub_transactions)
            )

        # A transaction with parts gets its amount from them
        has_parts = bool(subs) if subs is not None else transaction.has_sub_transactions
        if processed_action.set_amount and not has_parts:
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
            if value is None:
                transaction.category = None
            elif isinstance(value, int):
                transaction.category = TransactionCategory.objects.get(id=value)
            else:
                transaction.category = TransactionCategory.objects.get(name=value)

        if not transaction.id:
            _log("Transaction will be created as:")
        else:
            _log("Trasanction will be updated as:")

        _log(
            "{}".format(
                pformat(model_to_dict(transaction, exclude=["tags", "entities"])),
            )
        )
        transaction.save()
        if subs is not None:
            _save_sub_transactions(transaction, subs)

        # Handle M2M fields after save
        tags = []
        if processed_action.set_tags:
            tags = simple.eval(processed_action.set_tags)
            _log(f" And tags will be set as: {tags}")
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
            _log(f" And entities will be set as: {entities}")
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
                    transaction.entities.add(TransactionEntity.objects.get(id=entities))
                else:
                    transaction.entities.add(
                        TransactionEntity.objects.get(name=entities)
                    )

        dry_run_results.update_or_create_transaction(
            start_instance=starting_instance,
            end_instance=transaction,
            updated=existing,
            action=processed_action,
            query=search_query,
            entities=entities,
            tags=tags,
        )

        # transaction.full_clean()

    def _process_edit_transaction_action(transaction, processed_action) -> Transaction:
        dry_run_results.header("edit_transaction", action=processed_action)

        field = processed_action.field
        if field == TransactionRuleAction.Field.sub_transactions:
            original_value = list(transaction.sub_transactions.values("name", "amount"))
        else:
            original_value = getattr(transaction, field)
        new_value = simple.eval(processed_action.value)

        tags = []
        entities = []

        _log(
            f"Changing field '{field}' from '{original_value}' to '{new_value}'",
        )

        if field == TransactionRuleAction.Field.account:
            if isinstance(new_value, int):
                account = Account.objects.get(id=new_value)
                transaction.account = account
            elif isinstance(new_value, str):
                account = Account.objects.filter(name=new_value).first()
                transaction.account = account

        elif field == TransactionRuleAction.Field.category:
            if new_value is None:
                transaction.category = None
            elif isinstance(new_value, int):
                category = TransactionCategory.objects.get(id=new_value)
                transaction.category = category
            elif isinstance(new_value, str):
                category = TransactionCategory.objects.get(name=new_value)
                transaction.category = category

        elif field == TransactionRuleAction.Field.tags:
            transaction.tags.clear()

            if isinstance(new_value, list):
                for tag_value in new_value:
                    if isinstance(tag_value, int):
                        tag = TransactionTag.objects.get(id=tag_value)

                        transaction.tags.add(tag)
                        tags.append(tag)
                    elif isinstance(tag_value, str):
                        tag = TransactionTag.objects.get(name=tag_value)

                        transaction.tags.add(tag)
                        tags.append(tag)

            elif isinstance(new_value, (int, str)):
                if isinstance(new_value, int):
                    tag = TransactionTag.objects.get(id=new_value)
                else:
                    tag = TransactionTag.objects.get(name=new_value)

                transaction.tags.add(tag)
                tags.append(tag)

        elif field == TransactionRuleAction.Field.entities:
            transaction.entities.clear()
            if isinstance(new_value, list):
                for entity_value in new_value:
                    if isinstance(entity_value, int):
                        entity = TransactionEntity.objects.get(id=entity_value)

                        transaction.entities.add(entity)
                        entities.append(entity)
                    elif isinstance(entity_value, str):
                        entity = TransactionEntity.objects.get(name=entity_value)

                        transaction.entities.add(entity)
                        entities.append(entity)

            elif isinstance(new_value, (int, str)):
                if isinstance(new_value, int):
                    entity = TransactionEntity.objects.get(id=new_value)
                else:
                    entity = TransactionEntity.objects.get(name=new_value)

                transaction.entities.add(entity)
                entities.append(entity)

        elif field == TransactionRuleAction.Field.sub_transactions:
            subs = _evaluate_sub_transactions(transaction, new_value)
            if subs is not None:
                _save_sub_transactions(transaction, subs)
                new_value = ", ".join(f"{s.name}: {s.amount}" for s in subs) or "[]"

        elif (
            field == TransactionRuleAction.Field.amount
            and transaction.has_sub_transactions
        ):
            _log("Skipped: the amount is the sum of the transaction's sub-transactions")

        else:
            setattr(
                transaction,
                field,
                new_value,
            )

        dry_run_results.edit_transaction(
            instance=transaction,
            action=processed_action,
            old_value=original_value,
            new_value=new_value,
            field=field,
            tags=tags,
            entities=entities,
        )

        transaction.full_clean()

        return transaction

    def _process_rule(rule) -> bool:
        """Runs a rule against the instance. Returns whether its trigger matched."""
        nonlocal instance

        _log("Testing rule: {}".format(rule.name))
        if simple.eval(rule.trigger):
            _log("Initial trigger matched!")
            # For deleted transactions, we want to limit what actions can be performed
            if signal == "transaction_deleted":
                _log(
                    "Event is of type 'delete'. Only processing Update or Create actions..."
                )
                # Process only create/update actions, not edit actions
                for action in rule.update_or_create_transaction_actions.all():
                    try:
                        _log(
                            "Processing action with id {} and order {}...".format(
                                action.id, action.order
                            )
                        )
                        _process_update_or_create_transaction_action(
                            processed_action=action,
                        )
                    except Exception as e:
                        dry_run_results.error(
                            "Error raised: '{}'. Check the logs tab for more "
                            "information".format(e)
                        )
                        _log(
                            f"Error processing update or create transaction action {action.id} on deletion",
                            level="error",
                        )
            else:
                # Normal processing for non-deleted transactions
                edit_actions = list(rule.transaction_actions.all())
                update_or_create_actions = list(
                    rule.update_or_create_transaction_actions.all()
                )

                # Check if any action has a non-zero order
                has_custom_order = any(a.order > 0 for a in edit_actions) or any(
                    a.order > 0 for a in update_or_create_actions
                )

                if has_custom_order:
                    _log(
                        "One or more actions have a custom order, actions will be processed ordered by "
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
                                _log(
                                    "Processing 'edit_transaction' action with id {} and order {}...".format(
                                        action.id, action.order
                                    )
                                )
                                instance = _process_edit_transaction_action(
                                    transaction=instance,
                                    processed_action=action,
                                )

                                if rule.sequenced:
                                    # Update names for next actions
                                    simple.names.update(_get_names(instance))
                            else:
                                _log(
                                    "Processing 'update_or_create_transaction' action with id {} and order {}...".format(
                                        action.id, action.order
                                    )
                                )
                                _process_update_or_create_transaction_action(
                                    processed_action=action,
                                )
                                _clear_names("my_")
                        except Exception as e:
                            dry_run_results.error(
                                "Error raised: '{}'. Check the logs tab for more "
                                "information".format(e)
                            )
                            _log(
                                f"Error processing action {action.id}",
                                level="error",
                            )
                    # Save at the end
                    if signal != "transaction_deleted":
                        instance.save()
                else:
                    _log(
                        "No actions have a custom order, actions will be processed ordered by creation "
                        "date, with Edit actions running first, then Update or Create actions..."
                    )
                    # Original behavior
                    for action in edit_actions:
                        _log(
                            "Processing 'edit_transaction' action with id {}...".format(
                                action.id
                            )
                        )
                        try:
                            instance = _process_edit_transaction_action(
                                transaction=instance,
                                processed_action=action,
                            )
                            if rule.sequenced:
                                # Update names for next actions
                                simple.names.update(_get_names(instance))
                        except Exception as e:
                            dry_run_results.error(
                                "Error raised: '{}'. Check the logs tab for more "
                                "information".format(e)
                            )
                            _log(
                                f"Error processing edit transaction action {action.id}",
                                level="error",
                            )

                    if rule.sequenced:
                        # Update names for next actions
                        simple.names.update(_get_names(instance))
                    if signal != "transaction_deleted":
                        instance.save()

                    for action in update_or_create_actions:
                        _log(
                            "Processing 'update_or_create_transaction' action with id {}...".format(
                                action.id
                            )
                        )
                        try:
                            _process_update_or_create_transaction_action(
                                processed_action=action,
                            )
                            _clear_names("my_")
                        except Exception as e:
                            dry_run_results.error(
                                "Error raised: '{}'. Check the logs tab for more "
                                "information".format(e)
                            )
                            _log(
                                f"Error processing update or create transaction action {action.id}",
                                level="error",
                            )
        else:
            dry_run_results.error(
                error="Initial trigger didn't match, this rule will be skipped",
            )
            _log("Initial trigger didn't match, this rule will be skipped")
            return False

        return True

    user = get_user_model().objects.get(id=user_id)
    if not dry_run:
        write_current_user(user)
    logs = [] if dry_run else None
    dry_run_results = DryRunResults(dry_run=dry_run)

    if dry_run and not rule_id:
        raise Exception("Cannot dry run without a rule id")

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

            dry_run_results.triggering_transaction(instance)

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

            _log("Starting rule execution...")
            _log("Available functions: {}".format(functions.keys()))

            names = _get_names(instance)

            simple = EvalWithCompoundTypes(names=names, functions=functions)

            if signal == "transaction_updated" and old_data:
                simple.names.update(_get_names(old_data, "old_"))

            runnable_rules = TransactionRule.runnable_by(user)

            # Select rules based on the signal type
            if dry_run and rule_id:
                rules = TransactionRule.objects.filter(id=rule_id)
            elif signal == "transaction_manual":
                # Chosen by the user, so "active" and the "run on" switches don't apply
                rules = runnable_rules.filter(id__in=rule_ids or []).order_by(
                    "order", "id"
                )
            elif signal == "transaction_created":
                rules = runnable_rules.filter(active=True, on_create=True).order_by(
                    "order", "id"
                )
            elif signal == "transaction_updated":
                rules = runnable_rules.filter(active=True, on_update=True).order_by(
                    "order", "id"
                )
            elif signal == "transaction_deleted":
                rules = runnable_rules.filter(active=True, on_delete=True).order_by(
                    "order", "id"
                )
            else:
                rules = runnable_rules.filter(active=True).order_by("order", "id")

            _log("Testing {} rule(s)...".format(len(rules)))

            # Process the rules as before
            applied_rule_ids = []
            failed_rules = {}
            for rule in rules:
                if signal != "transaction_manual":
                    _process_rule(rule)
                    continue

                # A manual run touches the whole history, so a rule that fails is
                # rolled back for this transaction instead of being half applied
                names_before = dict(simple.names)
                errors_before = len(errors)
                try:
                    with db_transaction.atomic():
                        matched = _process_rule(rule)
                        if len(errors) > errors_before:
                            raise _RuleFailed
                    if matched:
                        applied_rule_ids.append(rule.id)
                except Exception as e:
                    if not isinstance(e, _RuleFailed):
                        _log(
                            f"Error processing rule {rule.id} on transaction {instance_id}",
                            level="error",
                        )
                    failed_rules[rule.id] = "; ".join(errors[errors_before:])
                    instance = Transaction.objects.get(id=instance_id)
                    simple.names = names_before

            if not dry_run and signal == "transaction_created":
                try:
                    apply_auto_tagging(instance, user)
                except Exception:
                    logger.error(
                        "Error while applying auto-tagging for transaction %s",
                        instance.id,
                        exc_info=True,
                    )
    except Exception as e:
        _log(
            "** Error while executing 'check_for_transaction_rules' task",
            level="error",
        )
        if not dry_run:
            delete_current_user()
            raise e

    if not dry_run:
        delete_current_user()

    if signal == "transaction_manual":
        return {"applied_rule_ids": applied_rule_ids, "failed_rules": failed_rules}

    return logs, dry_run_results.results


class _RuleFailed(Exception):
    pass


@app.task(name="run_rules_on_all_transactions")
def run_rules_on_all_transactions(run_id: int):
    """
    Applies the rules of a RuleRun to every transaction its owner has access to,
    oldest first, recording progress and results on the run.
    """
    run = RuleRun.objects.get(id=run_id)
    run.status = RuleRun.Status.PROCESSING
    run.save()

    try:
        _apply_run(run)
    except Exception:
        run.status = RuleRun.Status.FAILED
        raise
    else:
        run.status = RuleRun.Status.FINISHED
        logger.info(
            f"Finished rule run {run.id}: {run.total} transactions, "
            f"{run.applied} applied, {run.failed} failed, {run.skipped} skipped"
        )
    finally:
        run.finished_at = timezone.now()
        run.save()


def _apply_run(run: RuleRun):
    rules = {rule["id"]: rule for rule in run.rules}

    write_current_user(run.owner)
    try:
        with cachalot_disabled():
            # Taken up front: transactions created by the rules are not processed
            transaction_ids = list(
                Transaction.objects.order_by("date", "id").values_list("id", flat=True)
            )
    finally:
        delete_current_user()

    run.total = len(transaction_ids)
    run.save()
    last_saved = monotonic()

    for transaction_id in transaction_ids:
        try:
            result = check_for_transaction_rules(
                instance_id=transaction_id,
                user_id=run.owner_id,
                signal="transaction_manual",
                rule_ids=list(rules),
            )
        except Transaction.DoesNotExist:
            # Deleted while the run was in progress
            run.skipped += 1
        except Exception as e:
            # Already logged by the task, carry on with the remaining transactions
            run.failed += 1
            _record_failure(run, transaction_id, None, str(e))
        else:
            for rule_id in result["applied_rule_ids"]:
                rules[rule_id]["applied"] += 1
            for rule_id, error in result["failed_rules"].items():
                rules[rule_id]["failed"] += 1
                _record_failure(run, transaction_id, rules[rule_id]["name"], error)

            if result["failed_rules"]:
                run.failed += 1
            elif result["applied_rule_ids"]:
                run.applied += 1

        run.processed += 1

        # Throttled, the page polls every couple of seconds anyway
        if monotonic() - last_saved >= 1:
            run.save()
            last_saved = monotonic()


def _record_failure(run: RuleRun, transaction_id: int, rule_name, error: str):
    if len(run.failures) >= RuleRun.MAX_FAILURES:
        return

    transaction = Transaction.userless_all_objects.filter(id=transaction_id).first()
    run.failures.append(
        {
            "transaction_id": transaction_id,
            "date": transaction.date.isoformat() if transaction else None,
            "description": transaction.description if transaction else "",
            "rule": rule_name,
            "error": error[:500],
        }
    )
