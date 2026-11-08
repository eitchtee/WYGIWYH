import logging
from datetime import timedelta

from django.db.models import Min
from django.utils import timezone

from apps.bank_sync.models import BankSyncAccount, BankSyncService
from apps.common.functions.decimals import truncate_decimal
from apps.common.middleware.thread_local import delete_current_user, write_current_user
from apps.rules.signals import transaction_created
from apps.transactions.models import Transaction

logger = logging.getLogger(__name__)

# Banks post late and back-date transactions, so every sync looks this far back
OVERLAP_DAYS = 7
# How far apart a synced transaction and the one it matches can be dated
MATCH_DAYS = 3
# Pending ones older than this are taken as cancelled and no longer followed. A
# card's bill cycle is at most ~40 days
PENDING_MAX_DAYS = 60


def refresh_remote_accounts(service: BankSyncService, provider=None) -> None:
    """Mirror the provider's account list, keeping existing links.

    Accounts the provider no longer returns are dropped: their ids are gone for good.
    """
    provider = provider or service.get_provider()
    remote_accounts = {remote.id: remote for remote in provider.list_accounts()}
    service.accounts.exclude(external_id__in=remote_accounts).delete()

    for remote in remote_accounts.values():
        link, _ = BankSyncAccount.objects.get_or_create(
            service=service, external_id=remote.id
        )
        link.external_name = remote.name
        link.remote_error = remote.error
        link.available_currencies = sorted(
            set(link.available_currencies) | set(remote.currencies)
        )
        link.save()


def _match_existing(link: BankSyncAccount, internal_id, type_, amount, date) -> bool:
    """Tag a transaction the user already added instead of creating a new one."""
    candidates = Transaction.userless_all_objects.filter(
        account=link.account,
        type=type_,
        amount=truncate_decimal(amount, link.account.currency.decimal_places),
        date__range=(date - timedelta(days=MATCH_DAYS), date + timedelta(days=MATCH_DAYS)),
        internal_id__isnull=True,
        deleted=False,
    )
    best = min(candidates, key=lambda t: abs((t.date - date).days), default=None)
    if best is None:
        return False
    # Not a user edit, so no transaction_updated (it would run "on update" rules)
    Transaction.userless_all_objects.filter(pk=best.pk).update(
        emit_signal=False, internal_id=internal_id
    )
    return True


def _settle(transaction: Transaction, amount, date) -> None:
    """The bank posted a transaction that was still unpaid: take its final values.

    Happens once, so later edits stick. One marked paid by hand is left alone.
    """
    if transaction.is_paid or transaction.deleted:
        return
    # Only when it still follows the date, so one picked by the user is kept
    if transaction.reference_date == transaction.date.replace(day=1):
        transaction.reference_date = date.replace(day=1)
    transaction.is_paid = True
    transaction.amount = amount
    transaction.date = date
    # save() keeps a transfer's other side in step. It sends no signal, and as a
    # bank update rather than a user edit, rules don't run again
    transaction.save()


def _sync_account(service: BankSyncService, link: BankSyncAccount, provider) -> int:
    prefix = f"{service.service_type}:{link.external_id}:"
    start = link.start_date
    if link.last_synced_date:
        start = max(start, link.last_synced_date - timedelta(days=OVERLAP_DAYS))
    # Pending ones can post weeks later (a card's bill closing): look back far
    # enough to see it happen
    oldest_unpaid = Transaction.userless_all_objects.filter(
        internal_id__startswith=prefix,
        is_paid=False,
        deleted=False,
        date__gte=timezone.localdate() - timedelta(days=PENDING_MAX_DAYS),
    ).aggregate(Min("date"))["date__min"]
    if oldest_unpaid:
        start = min(start, oldest_unpaid)

    created = 0
    seen_currencies = set()
    for remote in provider.get_transactions(link.external_id, start):
        if remote.date < link.start_date:
            continue
        if remote.currency:
            seen_currencies.add(remote.currency)
            if link.currencies and remote.currency not in link.currencies:
                continue

        internal_id = prefix + remote.id
        type_ = (
            Transaction.Type.INCOME if remote.amount > 0 else Transaction.Type.EXPENSE
        )
        amount = abs(remote.amount)

        # userless_all_objects: also sees soft deleted ones, so deleting a synced
        # transaction doesn't bring it back on the next run
        existing = Transaction.userless_all_objects.filter(
            internal_id=internal_id
        ).first()
        if existing:
            if not remote.pending:
                _settle(existing, amount, remote.date)
            continue

        if service.match_existing and _match_existing(
            link, internal_id, type_, amount, remote.date
        ):
            continue

        transaction = Transaction.objects.create(
            account=link.account,
            owner=service.owner,
            type=type_,
            amount=amount,
            date=remote.date,
            description=remote.description[:500],
            notes=remote.notes,
            is_paid=not remote.pending,
            internal_id=internal_id,
        )
        created += 1
        if service.trigger_rules:
            transaction_created.send(sender=transaction)

    link.last_synced_date = timezone.localdate()
    link.available_currencies = sorted(set(link.available_currencies) | seen_currencies)
    link.save(update_fields=["last_synced_date", "available_currencies"])
    return created


def sync_service(service: BankSyncService) -> int:
    """Import new transactions for every linked account. Returns how many.

    A failing account doesn't stop the others. Any failure keeps last_sync as is,
    so the service is retried on the next run.
    """
    created = 0
    errors = []
    # Rules and the owned-object managers read the user from the thread
    write_current_user(service.owner)
    try:
        provider = service.get_provider()
        refresh_remote_accounts(service, provider)
        links = service.accounts.filter(
            account__isnull=False, start_date__isnull=False
        ).select_related("account__currency")
        for link in links:
            error = link.remote_error
            if not error:
                try:
                    created += _sync_account(service, link, provider)
                except Exception as e:
                    logger.exception(f"Bank sync failed for {service.name} / {link}")
                    error = str(e)
            link.last_error = error[:1000]
            link.save(update_fields=["last_error"])
            if error:
                errors.append(f"{link}: {error}")
    except Exception as e:
        logger.exception(f"Bank sync failed for {service.name}")
        errors.append(str(e))
    finally:
        delete_current_user()

    if errors:
        service.failure_count += 1
        service.last_error = "\n".join(errors)[:1000]
        service.save(update_fields=["failure_count", "last_error"])
    else:
        service.last_sync = timezone.now()
        service.failure_count = 0
        service.last_error = ""
        service.save(update_fields=["last_sync", "failure_count", "last_error"])
    logger.info(f"Bank sync for {service.name} created {created} transactions")
    return created


def is_due(service: BankSyncService) -> bool:
    if service.last_sync is None:
        return True
    # Hour granularity, the scheduler runs on the hour
    elapsed = timezone.now().replace(minute=0, second=0, microsecond=0) - (
        service.last_sync.replace(minute=0, second=0, microsecond=0)
    )
    return elapsed >= timedelta(hours=service.sync_interval)


def sync_due_services(force: bool = False) -> None:
    for service in BankSyncService.objects.filter(is_active=True):
        if force or is_due(service):
            sync_service(service)
