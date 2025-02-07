import logging

from cachalot.api import cachalot_disabled
from dateutil.relativedelta import relativedelta
from procrastinate.contrib.django import app
from simpleeval import EvalWithCompoundTypes

from apps.accounts.models import Account
from apps.rules.models import TransactionRule, TransactionRuleAction
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

            context = {
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
            }

            functions = {"relativedelta": relativedelta}

            simple = EvalWithCompoundTypes(names=context, functions=functions)

            if signal == "transaction_created":
                rules = TransactionRule.objects.filter(active=True, on_create=True)
            elif signal == "transaction_updated":
                rules = TransactionRule.objects.filter(active=True, on_update=True)
            else:
                rules = TransactionRule.objects.filter(active=True)

            for rule in rules:
                if simple.eval(rule.trigger):
                    for action in rule.transaction_actions.all():
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
                                simple.eval(action.value),
                            )

                        elif action.field == TransactionRuleAction.Field.account:
                            value = simple.eval(action.value)
                            if isinstance(value, int):
                                account = Account.objects.get(id=value)
                                instance.account = account
                            elif isinstance(value, str):
                                account = Account.objects.filter(name=value).first()
                                instance.account = account

                        elif action.field == TransactionRuleAction.Field.category:
                            value = simple.eval(action.value)
                            if isinstance(value, int):
                                category = TransactionCategory.objects.get(id=value)
                                instance.category = category
                            elif isinstance(value, str):
                                category = TransactionCategory.objects.get(name=value)
                                instance.category = category

                        elif action.field == TransactionRuleAction.Field.tags:
                            value = simple.eval(action.value)
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
                            value = simple.eval(action.value)
                            if isinstance(value, list):
                                # Clear existing entities
                                instance.entities.clear()
                                for entity_value in value:
                                    if isinstance(entity_value, int):
                                        entity = TransactionEntity.objects.get(
                                            id=entity_value
                                        )
                                        instance.entities.add(entity)
                                    elif isinstance(entity_value, str):
                                        entity = TransactionEntity.objects.get(
                                            name=entity_value
                                        )
                                        instance.entities.add(entity)

                            elif isinstance(value, (int, str)):
                                # If a single value is provided, treat it as a single entity
                                instance.entities.clear()
                                if isinstance(value, int):
                                    entity = TransactionEntity.objects.get(id=value)
                                else:
                                    entity = TransactionEntity.objects.get(name=value)

                                instance.entities.add(entity)

            instance.save()
    except Exception as e:
        logger.error(
            "Error while executing 'check_for_transaction_rules' task",
            exc_info=True,
        )
        raise e
