from decimal import Decimal

from django.db import transaction as db_transaction
from django.utils import timezone

from apps.accounts.models import Account
from apps.splits.models import (
    SplitEvent,
    SplitExpense,
    SplitParticipant,
    SplitPayment,
    SplitTransactionLink,
)
from apps.transactions.models import Transaction, TransactionCategory


def expected_transaction_type_for_kind(kind: str) -> str:
    if kind in (
        SplitTransactionLink.Kind.PAYMENT_IN,
        SplitTransactionLink.Kind.SETTLEMENT_IN,
    ):
        return Transaction.Type.INCOME
    return Transaction.Type.EXPENSE


def build_default_sync_description(
    *,
    event: SplitEvent,
    kind: str,
    expense: SplitExpense | None = None,
    payment: SplitPayment | None = None,
    counterparty: SplitParticipant | None = None,
) -> str:
    if expense is not None:
        return f"[{event.name}] {expense.description}"
    if payment is not None:
        if kind == SplitTransactionLink.Kind.PAYMENT_IN:
            return f"[{event.name}] Payment from {payment.from_participant.name}"
        return f"[{event.name}] Payment to {payment.to_participant.name}"
    if counterparty is not None:
        if kind == SplitTransactionLink.Kind.SETTLEMENT_IN:
            return f"[{event.name}] Receive from {counterparty.name}"
        return f"[{event.name}] Pay {counterparty.name}"
    return f"[{event.name}] Split transaction"


@db_transaction.atomic
def create_and_link_transaction(
    *,
    user,
    event: SplitEvent,
    kind: str,
    account: Account,
    amount: Decimal,
    date,
    description: str,
    is_paid: bool = True,
    category: TransactionCategory | None = None,
    tags=(),
    entities=(),
    notes: str = "",
    expense: SplitExpense | None = None,
    payment: SplitPayment | None = None,
    counterparty: SplitParticipant | None = None,
) -> SplitTransactionLink:
    tx_type = expected_transaction_type_for_kind(kind)
    tx = Transaction(
        owner=user,
        account=account,
        type=tx_type,
        is_paid=is_paid,
        date=date or timezone.localdate(),
        amount=amount,
        description=description[:500],
        notes=notes,
        category=category,
    )
    tx.save()
    tx.tags.set(tags)
    tx.entities.set(entities)

    return SplitTransactionLink.objects.create(
        event=event,
        user=user,
        transaction=tx,
        kind=kind,
        expense=expense,
        payment=payment,
        counterparty=counterparty,
    )


@db_transaction.atomic
def link_existing_transaction(
    *,
    user,
    event: SplitEvent,
    kind: str,
    tx: Transaction,
    expense: SplitExpense | None = None,
    payment: SplitPayment | None = None,
    counterparty: SplitParticipant | None = None,
) -> SplitTransactionLink:
    return SplitTransactionLink.objects.create(
        event=event,
        user=user,
        transaction=tx,
        kind=kind,
        expense=expense,
        payment=payment,
        counterparty=counterparty,
    )


@db_transaction.atomic
def settle_pending_links_for_payment(payment: SplitPayment) -> int:
    """When a SplitPayment is recorded, find any unpaid SETTLEMENT_OUT/SETTLEMENT_IN
    WYGIWYH transaction links for the sender or recipient matching this counterparty,
    mark those WYGIWYH transactions as paid, and attach them to this payment.
    """
    updated = 0
    # Sender's planned outgoing settlement to recipient
    if payment.from_participant.user_id:
        out_links = SplitTransactionLink.objects.select_related("transaction").filter(
            event=payment.event,
            user_id=payment.from_participant.user_id,
            kind=SplitTransactionLink.Kind.SETTLEMENT_OUT,
            counterparty=payment.to_participant,
            payment__isnull=True,
        )
        for link in out_links:
            tx = link.transaction
            if not tx.deleted and not tx.is_paid:
                tx.is_paid = True
                tx.date = payment.date
                tx.save()
            link.kind = SplitTransactionLink.Kind.PAYMENT_OUT
            link.payment = payment
            link.save(update_fields=["kind", "payment"])
            updated += 1

    # Recipient's planned incoming settlement from sender
    if payment.to_participant.user_id:
        in_links = SplitTransactionLink.objects.select_related("transaction").filter(
            event=payment.event,
            user_id=payment.to_participant.user_id,
            kind=SplitTransactionLink.Kind.SETTLEMENT_IN,
            counterparty=payment.from_participant,
            payment__isnull=True,
        )
        for link in in_links:
            tx = link.transaction
            if not tx.deleted and not tx.is_paid:
                tx.is_paid = True
                tx.date = payment.date
                tx.save()
            link.kind = SplitTransactionLink.Kind.PAYMENT_IN
            link.payment = payment
            link.save(update_fields=["kind", "payment"])
            updated += 1

    return updated
