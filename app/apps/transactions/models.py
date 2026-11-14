import calendar
import decimal
import functools
import logging
import operator
import uuid
from copy import deepcopy
from pathlib import Path

from apps.common.fields.month_year import MonthYearModelField
from apps.common.functions.decimals import truncate_decimal
from apps.common.middleware.thread_local import get_current_user
from apps.common.models import (
    OwnedObject,
    OwnedObjectManager,
    SharedObject,
    SharedObjectManager,
)
from apps.common.templatetags.decimal import drop_trailing_zeros, localize_number
from apps.currencies.utils.convert import convert
from apps.transactions.storage import PrivateMediaStorage
from apps.transactions.validators import validate_decimal_places, validate_non_negative
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import Q
from django.db.models.signals import post_delete
from django.dispatch import Signal, receiver
from django.template.defaultfilters import date
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger()

transaction_created = Signal()
transaction_updated = Signal()
transaction_deleted = Signal()


class FilterPreset(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="filter_presets",
    )
    name = models.CharField(max_length=100)
    parameters = models.JSONField(default=dict)

    class Meta:
        ordering = ["name", "id"]

    def __str__(self):
        return self.name


def transaction_attachment_path(instance, filename):
    extension = Path(filename).suffix
    return f"transaction_attachments/{instance.transaction_id}/{instance.id}{extension}"


class SoftDeleteQuerySet(models.QuerySet):
    @staticmethod
    def _emit_signals(instances, created=False, old_data=None):
        """Helper to emit signals for multiple instances"""
        for i, instance in enumerate(instances):
            if created:
                transaction_created.send(sender=instance)
            else:
                transaction_updated.send(sender=instance, old_data=old_data[i])

    def bulk_create(self, objs, emit_signal=True, **kwargs):
        instances = super().bulk_create(objs, **kwargs)

        if emit_signal:
            self._emit_signals(instances, created=True)

        return instances

    def bulk_update(self, objs, fields, emit_signal=True, **kwargs):
        old_data = deepcopy(objs)
        result = super().bulk_update(objs, fields, **kwargs)

        if emit_signal:
            self._emit_signals(objs, created=False, old_data=old_data)

        return result

    def update(self, emit_signal=True, **kwargs):
        # Get instances before update
        instances = list(self)
        old_data = deepcopy(instances)

        result = super().update(**kwargs)

        if emit_signal:
            # Refresh instances to get new values
            refreshed = self.model.objects.filter(pk__in=[obj.pk for obj in instances])
            self._emit_signals(refreshed, created=False, old_data=old_data)

        return result

    def delete(self):
        if not settings.ENABLE_SOFT_DELETE:
            # Get instances before hard delete
            instances = list(self)
            # Send signals for each instance before deletion
            for instance in instances:
                transaction_deleted.send(sender=instance)
            # Perform hard delete
            result = super().delete()
            return result

        # Separate the queryset into already deleted and not deleted objects
        already_deleted = self.filter(deleted=True)
        not_deleted = self.filter(deleted=False)

        # Use a transaction to ensure atomicity
        with transaction.atomic():
            # Get instances for hard delete before they're gone
            already_deleted_instances = list(already_deleted)
            for instance in already_deleted_instances:
                transaction_deleted.send(sender=instance)

            # Perform hard delete on already deleted objects
            hard_deleted_count = already_deleted._raw_delete(already_deleted.db)

            # Get instances for soft delete
            instances_to_soft_delete = list(not_deleted)

            # Perform soft delete on not deleted objects
            soft_deleted_count = not_deleted.update(
                deleted=True, deleted_at=timezone.now()
            )

            # Send signals for soft deleted instances
            for instance in instances_to_soft_delete:
                instance.deleted = True
                instance.deleted_at = timezone.now()
                transaction_deleted.send(sender=instance)

        # Return a tuple of counts as expected by Django's delete method
        return (
            hard_deleted_count + soft_deleted_count,
            {"Transaction": hard_deleted_count + soft_deleted_count},
        )

    def hard_delete(self):
        return super().delete()

    def collapse_transfers(self):
        # A transfer is listed once: drop its income side when the expense side is also listed
        if not Transaction.transfers_combined():
            return self
        return self.exclude(
            type=Transaction.Type.INCOME,
            linked_transaction__type=Transaction.Type.EXPENSE,
            linked_transaction__in=self.values("pk"),
        )


class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        qs = SoftDeleteQuerySet(self.model, using=self._db)
        user = get_current_user()
        if user and not user.is_anonymous:
            account_ids = (
                qs.filter(
                    Q(account__visibility="public")
                    | Q(account__owner=user)
                    | Q(account__shared_with=user)
                    | Q(account__visibility="private", account__owner=None),
                    deleted=False,
                )
                .values_list("account__id", flat=True)
                .distinct()
            )

            return qs.filter(account_id__in=account_ids, deleted=False)

        else:
            return qs.filter(
                deleted=False,
            )


class AllObjectsManager(models.Manager):
    def get_queryset(self):
        user = get_current_user()
        if user and not user.is_anonymous:
            return (
                SoftDeleteQuerySet(self.model, using=self._db)
                .filter(
                    Q(account__visibility="public")
                    | Q(account__owner=user)
                    | Q(account__shared_with=user)
                    | Q(account__visibility="private", account__owner=None),
                )
                .distinct()
            )
        else:
            return SoftDeleteQuerySet(self.model, using=self._db)


class UserlessAllObjectsManager(models.Manager):
    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db)


class DeletedObjectsManager(models.Manager):
    def get_queryset(self):
        qs = SoftDeleteQuerySet(self.model, using=self._db)
        user = get_current_user()
        if user and not user.is_anonymous:
            return qs.filter(
                Q(account__visibility="public")
                | Q(account__owner=user)
                | Q(account__shared_with=user)
                | Q(account__visibility="private", account__owner=None),
                deleted=True,
            ).distinct()
        else:
            return qs.filter(
                deleted=True,
            )


class UserlessDeletedObjectsManager(models.Manager):
    def get_queryset(self):
        qs = SoftDeleteQuerySet(self.model, using=self._db)
        return qs.filter(
            deleted=True,
        )


class GenericAccountOwnerManager(models.Manager):
    def get_queryset(self):
        queryset = super().get_queryset()
        user = get_current_user()
        if user and not user.is_anonymous:
            return queryset.filter(
                Q(account__visibility="public")
                | Q(account__owner=user)
                | Q(account__shared_with=user)
                | Q(account__visibility="private", account__owner=None),
            ).distinct()
        return queryset.none()


class TransactionCategory(SharedObject):
    name = models.CharField(max_length=255, verbose_name=_("Name"))
    mute = models.BooleanField(default=False, verbose_name=_("Mute"))
    active = models.BooleanField(
        default=True,
        verbose_name=_("Active"),
        help_text=_(
            "Deactivated categories won't be able to be selected when creating new transactions"
        ),
    )

    objects = SharedObjectManager()
    all_objects = models.Manager()  # Unfiltered manager

    class Meta:
        verbose_name = _("Transaction Category")
        verbose_name_plural = _("Transaction Categories")
        db_table = "t_categories"
        unique_together = (("owner", "name"),)
        ordering = ["name", "id"]

    def __str__(self):
        return self.name


class TransactionTag(SharedObject):
    name = models.CharField(max_length=255, verbose_name=_("Name"))
    active = models.BooleanField(
        default=True,
        verbose_name=_("Active"),
        help_text=_(
            "Deactivated tags won't be able to be selected when creating new transactions"
        ),
    )

    objects = SharedObjectManager()
    all_objects = models.Manager()  # Unfiltered manager

    class Meta:
        verbose_name = _("Transaction Tags")
        verbose_name_plural = _("Transaction Tags")
        db_table = "tags"
        unique_together = (("owner", "name"),)
        ordering = ["name", "id"]

    def __str__(self):
        return self.name


class TransactionEntity(SharedObject):
    name = models.CharField(max_length=255, verbose_name=_("Name"))
    active = models.BooleanField(
        default=True,
        verbose_name=_("Active"),
        help_text=_(
            "Deactivated entities won't be able to be selected when creating new transactions"
        ),
    )

    objects = SharedObjectManager()
    all_objects = models.Manager()  # Unfiltered manager

    class Meta:
        verbose_name = _("Entity")
        verbose_name_plural = _("Entities")
        db_table = "entities"
        unique_together = (("owner", "name"),)
        ordering = ["name", "id"]

    def __str__(self):
        return self.name


class Transaction(OwnedObject):
    class Type(models.TextChoices):
        INCOME = "IN", _("Income")
        EXPENSE = "EX", _("Expense")

    account = models.ForeignKey(
        "accounts.Account",
        on_delete=models.CASCADE,
        verbose_name=_("Account"),
        related_name="transactions",
    )
    type = models.CharField(
        max_length=2,
        choices=Type,
        default=Type.EXPENSE,
        verbose_name=_("Type"),
    )
    is_paid = models.BooleanField(default=True, verbose_name=_("Paid"))
    date = models.DateField(verbose_name=_("Date"))
    reference_date = MonthYearModelField(verbose_name=_("Reference Date"))
    mute = models.BooleanField(default=False, verbose_name=_("Mute"))

    amount = models.DecimalField(
        max_digits=42,
        decimal_places=30,
        verbose_name=_("Amount"),
        validators=[validate_non_negative, validate_decimal_places],
    )

    description = models.CharField(
        max_length=500, verbose_name=_("Description"), blank=True
    )
    notes = models.TextField(blank=True, verbose_name=_("Notes"))
    category = models.ForeignKey(
        TransactionCategory,
        on_delete=models.SET_NULL,
        verbose_name=_("Category"),
        blank=True,
        null=True,
    )
    tags = models.ManyToManyField(
        TransactionTag,
        verbose_name=_("Tags"),
        blank=True,
    )
    entities = models.ManyToManyField(
        TransactionEntity,
        verbose_name=_("Entities"),
        blank=True,
        related_name="transactions",
    )

    installment_plan = models.ForeignKey(
        "InstallmentPlan",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="transactions",
        verbose_name=_("Installment Plan"),
    )
    installment_id = models.PositiveIntegerField(null=True, blank=True)
    recurring_transaction = models.ForeignKey(
        "RecurringTransaction",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="transactions",
        verbose_name=_("Recurring Transaction"),
    )
    linked_transaction = models.OneToOneField(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("Linked Transaction"),
    )
    internal_note = models.TextField(blank=True, verbose_name=_("Internal Note"))
    internal_id = models.TextField(
        blank=True, null=True, unique=True, verbose_name=_("Internal ID")
    )

    deleted = models.BooleanField(
        default=False, verbose_name=_("Deleted"), db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Deleted At")
    )

    objects = SoftDeleteManager.from_queryset(SoftDeleteQuerySet)()
    all_objects = AllObjectsManager.from_queryset(SoftDeleteQuerySet)()
    userless_all_objects = UserlessAllObjectsManager.from_queryset(SoftDeleteQuerySet)()
    deleted_objects = DeletedObjectsManager.from_queryset(SoftDeleteQuerySet)()
    userless_deleted_objects = UserlessDeletedObjectsManager.from_queryset(
        SoftDeleteQuerySet
    )()

    class Meta:
        verbose_name = _("Transaction")
        verbose_name_plural = _("Transactions")
        db_table = "transactions"
        default_manager_name = "objects"

    def clean(self):
        super().clean()

        # Convert empty internal_id to None to allow multiple "empty" values with unique constraint
        if self.internal_id == "":
            self.internal_id = None

        # Only process amount and reference_date if account exists
        # If account is missing, Django's required field validation will handle it
        try:
            account = self.account
        except Transaction.account.RelatedObjectDoesNotExist:
            # Account doesn't exist, skip processing that depends on it
            # Django will add the required field error
            return

        # Validate and normalize amount
        if isinstance(self.amount, (str, int, float)):
            self.amount = decimal.Decimal(str(self.amount))

        if self.amount is not None:  # missing amount is reported by field validation
            self.amount = truncate_decimal(
                value=self.amount, decimal_places=account.currency.decimal_places
            )

        # Normalize reference_date
        if self.reference_date:
            self.reference_date = self.reference_date.replace(day=1)
        elif not self.reference_date and self.date:
            self.reference_date = self.date.replace(day=1)

    def save(self, *args, sync_partner=True, **kwargs):
        # This is here so Django validation doesn't trigger an error before clean() is ran
        if not self.reference_date and self.date:
            self.reference_date = self.date.replace(day=1)

        # This is not recommended as it will run twice on some cases like form and API saves.
        # We only do this here because we forgot to independently call it on multiple places.
        self.full_clean()
        super().save(*args, **kwargs)

        # Both sides of a transfer share date, reference date, paid and mute state.
        # all_objects: never reach a side the current user can no longer see.
        if sync_partner and self.linked_transaction_id:
            Transaction.all_objects.filter(
                pk=self.linked_transaction_id
            ).exclude(
                date=self.date,
                reference_date=self.reference_date,
                is_paid=self.is_paid,
                mute=self.mute,
            ).update(
                date=self.date,
                reference_date=self.reference_date,
                is_paid=self.is_paid,
                mute=self.mute,
            )

    @staticmethod
    def transfers_combined():
        """The current user's "Combine transfers" setting (on when unknown)."""
        try:
            return get_current_user().settings.combine_transfers
        except (AttributeError, ObjectDoesNotExist):
            return True

    @property
    def shown_as_transfer(self):
        return bool(self.linked_transaction_id) and self.transfers_combined()

    @property
    def display_transaction(self):
        """The side a listing renders: the "from" side for a combined transfer."""
        return self.transfer_from if self.shown_as_transfer else self

    def add_transfer_side(self, account, amount):
        """Creates the "to" side of a transfer for this saved "from" (expense) transaction."""
        to_transaction = self.deepcopy()
        to_transaction.account = account
        to_transaction.type = Transaction.Type.INCOME
        to_transaction.amount = amount
        to_transaction.linked_transaction = self
        to_transaction.save()
        self.linked_transaction = to_transaction
        self.save()
        return to_transaction

    def transfer_link_error(self, other):
        """Why ``self`` and ``other`` can't be joined into a transfer, or None."""
        if self.linked_transaction_id == other.pk and other.linked_transaction_id == self.pk:
            return None
        if {self.type, other.type} != {self.Type.INCOME, self.Type.EXPENSE}:
            return _("A transfer needs one expense and one income.")
        if self.account_id == other.account_id:
            return _("A transfer needs two different accounts.")
        if self.linked_transaction_id not in (None, other.pk) or (
            other.linked_transaction_id not in (None, self.pk)
        ):
            return _("This transaction is already part of another transfer.")
        return None

    def link_transfer(self, other):
        """Joins an existing expense and income into a transfer."""
        error = self.transfer_link_error(other)
        if error:
            raise ValidationError(error)
        # update(): only the link changes; dates, amounts and rules are left alone
        Transaction.all_objects.filter(pk=self.pk).update(linked_transaction=other)
        Transaction.all_objects.filter(pk=other.pk).update(linked_transaction=self)
        self.linked_transaction, other.linked_transaction = other, self

    @property
    def transfer_from(self):
        if self.linked_transaction_id and self.type == self.Type.INCOME:
            return self.linked_transaction
        return self

    @property
    def transfer_to(self):
        if self.linked_transaction_id and self.type == self.Type.EXPENSE:
            return self.linked_transaction
        return self

    def delete(self, *args, _with_partner=True, **kwargs):
        # Transfers are deleted as a pair
        if _with_partner and self.linked_transaction_id:
            partner = Transaction.all_objects.filter(
                pk=self.linked_transaction_id
            ).first()
            if partner:
                partner.delete(_with_partner=False)

        if settings.ENABLE_SOFT_DELETE:
            if not self.deleted:
                self.deleted = True
                self.deleted_at = timezone.now()
                self.save()
                transaction_deleted.send(sender=self)  # Emit signal for soft delete
            else:
                result = super().delete(*args, **kwargs)
                return result
        else:
            # For hard delete mode
            transaction_deleted.send(sender=self)  # Emit signal before hard delete
            return super().delete(*args, **kwargs)

    def hard_delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)

    @property
    def has_sub_transactions(self):
        return bool(self.pk) and self.sub_transactions.exists()

    @property
    def saved_sub_transactions(self):
        """Sub-transactions, or none for an unsaved preview (which can't query them)."""
        return self.sub_transactions.all() if self.pk else []

    def copy_sub_transactions_from(self, source):
        """Makes this transaction's sub-transactions copies of ``source``'s (a
        transaction or a template that generates them)."""
        self.sub_transactions.all().delete()
        SubTransaction.objects.bulk_create(
            SubTransaction(transaction=self, name=sub.name, amount=sub.amount)
            for sub in source.sub_transactions.all()
        )

    def exchanged_amount(self):
        return self._exchanged_to(
            self.account.exchange_currency or self.account.currency.exchange_currency
        )

    def displayed_exchanged_amount(self):
        """The exchanged amount to display, or None when it's hidden."""
        return self._exchanged_to(self.account.displayed_exchange_currency)

    def _exchanged_to(self, exchange_currency):
        if not exchange_currency:
            return None

        converted_amount, prefix, suffix, decimal_places = convert(
            self.amount,
            to_currency=exchange_currency,
            from_currency=self.account.currency,
            date=self.date,
        )
        if converted_amount:
            return {
                "amount": converted_amount,
                "prefix": prefix,
                "suffix": suffix,
                "decimal_places": decimal_places,
            }

        return None

    def __str__(self):
        type_display = self.get_type_display()
        frmt_date = date(self.date, "SHORT_DATE_FORMAT")
        account = self.account
        tags = (
            ", ".join([x.name for x in self.tags.all()])
            if self.id
            else None or _("No tags")
        )
        category = self.category or _("No category")
        amount = localize_number(drop_trailing_zeros(self.amount))
        description = self.description or _("No description")
        return f"[{frmt_date}][{type_display}][{account}] {description} • {category} • {tags} • {amount}"

    def deepcopy(self, memo=None):
        """
        Creates a deep copy of the transaction instance.

        This method returns a new, unsaved Transaction instance with the same
        values as the original, including its many-to-many relationships.
        The primary key and any other unique fields are reset to avoid
        database integrity errors upon saving.
        """
        if memo is None:
            memo = {}

        # Create a new instance of the class
        new_obj = self.__class__()
        memo[id(self)] = new_obj

        # Copy all concrete fields from the original to the new object
        for field in self._meta.concrete_fields:
            # Skip the primary key to allow the database to generate a new one
            if field.primary_key:
                continue

            # Reset any unique fields to None to avoid constraint violations
            if field.unique and field.name in ("internal_id", "linked_transaction"):
                setattr(new_obj, field.name, None)
                continue

            # Copy the value of the field
            setattr(new_obj, field.name, getattr(self, field.name))

        # Save the new object to the database to get a primary key
        new_obj.save()

        # Copy the many-to-many relationships
        for field in self._meta.many_to_many:
            source_manager = getattr(self, field.name)
            destination_manager = getattr(new_obj, field.name)
            # Set the M2M relationships for the new object
            destination_manager.set(source_manager.all())

        return new_obj


SUB_TRANSACTION_PARENTS = (
    "transaction",
    "recurring_transaction",
    "installment_plan",
    "quick_transaction",
)


class SubTransaction(models.Model):
    """A named part of a transaction, or of a template that generates them; when
    present, the parts add up to its amount. Exactly one parent is set.

    Soft deletion follows the parent: sub-transactions are only reached through it.
    """

    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="sub_transactions",
        verbose_name=_("Transaction"),
    )
    recurring_transaction = models.ForeignKey(
        "RecurringTransaction",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="sub_transactions",
    )
    installment_plan = models.ForeignKey(
        "InstallmentPlan",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="sub_transactions",
    )
    quick_transaction = models.ForeignKey(
        "QuickTransaction",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="sub_transactions",
    )
    name = models.CharField(max_length=255, verbose_name=_("Name"))
    amount = models.DecimalField(
        max_digits=42,
        decimal_places=30,
        verbose_name=_("Amount"),
        validators=[validate_non_negative, validate_decimal_places],
    )

    class Meta:
        verbose_name = _("Sub-transaction")
        verbose_name_plural = _("Sub-transactions")
        db_table = "sub_transactions"
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                # One of: only "transaction" set, only "recurring_transaction" set, ...
                condition=functools.reduce(
                    operator.or_,
                    (
                        Q(**{f"{p}__isnull": p != parent for p in SUB_TRANSACTION_PARENTS})
                        for parent in SUB_TRANSACTION_PARENTS
                    ),
                ),
                name="sub_transaction_has_one_parent",
            )
        ]

    def __str__(self):
        return self.name


class TransactionAttachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.CASCADE,
        related_name="attachments",
        verbose_name=_("Transaction"),
    )
    file = models.FileField(
        upload_to=transaction_attachment_path,
        storage=PrivateMediaStorage(),
        verbose_name=_("File"),
    )
    original_name = models.CharField(max_length=255, verbose_name=_("Original Name"))
    content_type = models.CharField(
        max_length=255, blank=True, verbose_name=_("Content Type")
    )
    size = models.PositiveBigIntegerField(default=0, verbose_name=_("Size"))
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="transaction_attachments",
        verbose_name=_("Uploaded By"),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Transaction Attachment")
        verbose_name_plural = _("Transaction Attachments")
        db_table = "transaction_attachments"
        ordering = ["-created_at", "original_name"]

    def save(self, *args, **kwargs):
        if self.file:
            if not self.original_name:
                self.original_name = Path(self.file.name).name
            if not self.size:
                self.size = self.file.size
            if not self.content_type:
                self.content_type = getattr(self.file.file, "content_type", "")
        super().save(*args, **kwargs)

    def __str__(self):
        return self.original_name


@receiver(post_delete, sender=TransactionAttachment)
def delete_transaction_attachment_file(sender, instance, **kwargs):
    if not instance.file.name:
        return

    storage = instance.file.storage
    if storage.exists(instance.file.name):
        storage.delete(instance.file.name)


class InstallmentPlan(models.Model):
    class Recurrence(models.TextChoices):
        YEARLY = "yearly", _("Yearly")
        MONTHLY = "monthly", _("Monthly")
        WEEKLY = "weekly", _("Weekly")
        DAILY = "daily", _("Daily")

    account = models.ForeignKey(
        "accounts.Account", on_delete=models.CASCADE, verbose_name=_("Account")
    )
    type = models.CharField(
        max_length=10,
        choices=Transaction.Type,
        verbose_name=_("Type"),
    )
    description = models.CharField(max_length=500, verbose_name=_("Description"))
    number_of_installments = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        verbose_name=_("Number of Installments"),
        default=1,
    )
    installment_start = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        verbose_name=_("Installment Start"),
        help_text=_("The installment number to start counting from"),
        blank=True,
        default=1,
    )
    installment_total_number = models.PositiveIntegerField()
    start_date = models.DateField(verbose_name=_("Start Date"))
    reference_date = models.DateField(
        verbose_name=_("Reference Date"), null=True, blank=True
    )
    end_date = models.DateField(verbose_name=_("End Date"), null=True, blank=True)
    recurrence = models.CharField(
        max_length=10,
        choices=Recurrence,
        default=Recurrence.MONTHLY,
        verbose_name=_("Recurrence"),
    )
    installment_amount = models.DecimalField(
        max_digits=42, decimal_places=30, verbose_name=_("Installment Amount")
    )
    category = models.ForeignKey(
        "TransactionCategory",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Category"),
    )
    tags = models.ManyToManyField(TransactionTag, verbose_name=_("Tags"), blank=True)
    entities = models.ManyToManyField(
        TransactionEntity,
        verbose_name=_("Entities"),
        blank=True,
    )

    notes = models.TextField(blank=True, verbose_name=_("Notes"))

    add_description_to_transaction = models.BooleanField(
        default=True, verbose_name=_("Add description to transactions")
    )
    add_notes_to_transaction = models.BooleanField(
        default=True, verbose_name=_("Add notes to transactions")
    )

    all_objects = models.Manager()  # Unfiltered manager
    objects = GenericAccountOwnerManager()  # Default filtered manager

    class Meta:
        verbose_name = _("Installment Plan")
        verbose_name_plural = _("Installment Plans")

    def __str__(self):
        return self.description

    def save(self, *args, **kwargs):
        if not self.reference_date:
            self.reference_date = self.start_date

        if not self.installment_start:
            self.installment_start = 1

        self.end_date = self._calculate_end_date()
        self.installment_total_number = self._calculate_installment_total_number()

        instance = super().save(*args, **kwargs)
        return instance

    def _calculate_end_date(self):
        if self.recurrence == self.Recurrence.YEARLY:
            delta = relativedelta(years=self.number_of_installments - 1)
        elif self.recurrence == self.Recurrence.MONTHLY:
            delta = relativedelta(months=self.number_of_installments - 1)
        elif self.recurrence == self.Recurrence.WEEKLY:
            delta = relativedelta(weeks=self.number_of_installments - 1)
        else:
            delta = relativedelta(days=self.number_of_installments - 1)

        return self.start_date + delta

    def _calculate_installment_total_number(self):
        return self.number_of_installments + (self.installment_start - 1)

    @transaction.atomic
    def create_transactions(self):
        self.transactions.all().delete()

        for i in range(
            self.installment_start,
            self.installment_total_number + 1,
        ):
            if self.recurrence == self.Recurrence.YEARLY:
                delta = relativedelta(years=i - self.installment_start)
            elif self.recurrence == self.Recurrence.MONTHLY:
                delta = relativedelta(months=i - self.installment_start)
            elif self.recurrence == self.Recurrence.WEEKLY:
                delta = relativedelta(weeks=i - self.installment_start)
            else:
                delta = relativedelta(days=i - self.installment_start)

            transaction_date = self.start_date + delta
            transaction_reference_date = (self.reference_date + delta).replace(day=1)
            new_transaction = Transaction.all_objects.create(
                account=self.account,
                type=self.type,
                date=transaction_date,
                is_paid=False,
                reference_date=transaction_reference_date,
                amount=self.installment_amount,
                description=(
                    self.description if self.add_description_to_transaction else ""
                ),
                category=self.category,
                installment_plan=self,
                installment_id=i,
                notes=self.notes if self.add_notes_to_transaction else "",
                owner=self.account.owner,
            )
            new_transaction.tags.set(self.tags.all())
            new_transaction.entities.set(self.entities.all())
            new_transaction.copy_sub_transactions_from(self)

    @transaction.atomic
    def update_transactions(self):
        existing_transactions = self.transactions.all().order_by("installment_id")

        for i in range(self.installment_start, self.installment_total_number + 1):
            if self.recurrence == self.Recurrence.YEARLY:
                delta = relativedelta(years=i - self.installment_start)
            elif self.recurrence == self.Recurrence.MONTHLY:
                delta = relativedelta(months=i - self.installment_start)
            elif self.recurrence == self.Recurrence.WEEKLY:
                delta = relativedelta(weeks=i - self.installment_start)
            else:
                delta = relativedelta(days=i - self.installment_start)

            transaction_date = self.start_date + delta
            transaction_reference_date = (self.reference_date + delta).replace(day=1)

            # Get the existing transaction or None if it doesn't exist
            existing_transaction = existing_transactions.filter(
                installment_id=i
            ).first()

            if existing_transaction:
                # Update existing transaction
                existing_transaction.account = self.account
                existing_transaction.type = self.type
                existing_transaction.date = transaction_date
                existing_transaction.reference_date = transaction_reference_date
                existing_transaction.description = (
                    self.description if self.add_description_to_transaction else ""
                )
                existing_transaction.category = self.category
                existing_transaction.notes = (
                    self.notes if self.add_notes_to_transaction else ""
                )

                if (
                    not existing_transaction.is_paid
                ):  # Don't update value for paid transactions
                    existing_transaction.amount = self.installment_amount
                    existing_transaction.copy_sub_transactions_from(self)

                existing_transaction.save()

                # Update tags
                existing_transaction.tags.set(self.tags.all())
                existing_transaction.entities.set(self.entities.all())
            else:
                # If the transaction doesn't exist, create a new one
                new_transaction = Transaction.all_objects.create(
                    account=self.account,
                    type=self.type,
                    date=transaction_date,
                    is_paid=False,
                    reference_date=transaction_reference_date,
                    amount=self.installment_amount,
                    description=(
                        self.description if self.add_description_to_transaction else ""
                    ),
                    category=self.category,
                    installment_plan=self,
                    installment_id=i,
                    notes=self.notes if self.add_notes_to_transaction else "",
                    owner=self.account.owner,
                )
                new_transaction.tags.set(self.tags.all())
                new_transaction.entities.set(self.entities.all())
                new_transaction.copy_sub_transactions_from(self)

        # Remove any extra transactions that are no longer part of the plan
        self.transactions.filter(
            Q(installment_id__gt=self.installment_total_number)
            | Q(installment_id__lt=self.installment_start)
        ).delete()

    def delete(self, *args, **kwargs):
        # Delete related transactions
        self.transactions.all().delete()
        super().delete(*args, **kwargs)


class TransferTemplate(models.Model):
    """Lets a recurring or quick transaction of type Transfer generate linked transfers."""

    to_account = models.ForeignKey(
        "accounts.Account",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("To account"),
    )
    to_amount = models.DecimalField(
        max_digits=42,
        decimal_places=30,
        null=True,
        blank=True,
        verbose_name=_("To amount"),
        help_text=_("Leave empty to use the same amount"),
        validators=[validate_non_negative, validate_decimal_places],
    )

    class Meta:
        abstract = True

    @property
    def is_transfer(self):
        return self.type == self.Type.TRANSFER

    @property
    def transaction_type(self):
        """Type of the generated transaction: a transfer starts with its expense side."""
        return Transaction.Type.EXPENSE if self.is_transfer else self.type

    def clean(self):
        super().clean()
        if self.is_transfer:
            if not self.to_account_id:
                raise ValidationError({"to_account": _("This field is required.")})
            if self.to_account_id == self.account_id:
                raise ValidationError(
                    {"to_account": _("From and To accounts must be different.")}
                )

    def complete_transfer(self, transaction):
        """Adds the "to" side when this generates transfers."""
        if self.is_transfer and self.to_account_id:
            return transaction.add_transfer_side(
                self.to_account, self.to_amount or self.amount
            )


class RecurringTransaction(TransferTemplate):
    class Type(models.TextChoices):
        INCOME = "IN", _("Income")
        TRANSFER = "TR", _("Transfer")
        EXPENSE = "EX", _("Expense")

    class RecurrenceType(models.TextChoices):
        DAY = "day", _("day(s)")
        WEEK = "week", _("week(s)")
        MONTH = "month", _("month(s)")
        YEAR = "year", _("year(s)")

    is_paused = models.BooleanField(default=False, verbose_name=_("Paused"))
    account = models.ForeignKey(
        "accounts.Account", on_delete=models.CASCADE, verbose_name=_("Account")
    )
    type = models.CharField(
        max_length=2,
        choices=Type,
        default=Type.EXPENSE,
        verbose_name=_("Type"),
    )
    amount = models.DecimalField(
        max_digits=42,
        decimal_places=30,
        verbose_name=_("Amount"),
        validators=[validate_non_negative, validate_decimal_places],
    )
    description = models.CharField(max_length=500, verbose_name=_("Description"))
    category = models.ForeignKey(
        TransactionCategory,
        on_delete=models.SET_NULL,
        verbose_name=_("Category"),
        blank=True,
        null=True,
    )
    tags = models.ManyToManyField(TransactionTag, verbose_name=_("Tags"), blank=True)
    entities = models.ManyToManyField(
        TransactionEntity,
        verbose_name=_("Entities"),
        blank=True,
    )
    notes = models.TextField(blank=True, verbose_name=_("Notes"))
    reference_date = models.DateField(
        verbose_name=_("Reference Date"), null=True, blank=True
    )

    # Recurrence fields
    start_date = models.DateField(verbose_name=_("Start Date"))
    end_date = models.DateField(verbose_name=_("End Date"), null=True, blank=True)
    recurrence_type = models.CharField(
        max_length=7, choices=RecurrenceType, verbose_name=_("Recurrence Type")
    )
    recurrence_interval = models.PositiveIntegerField(
        verbose_name=_("Recurrence Interval"),
    )
    keep_at_most = models.PositiveIntegerField(
        verbose_name=_("Keep at most"), default=6, validators=[MinValueValidator(1)]
    )

    last_generated_date = models.DateField(
        verbose_name=_("Last Generated Date"), null=True, blank=True
    )
    last_generated_reference_date = models.DateField(
        verbose_name=_("Last Generated Reference Date"), null=True, blank=True
    )

    add_description_to_transaction = models.BooleanField(
        default=True, verbose_name=_("Add description to transactions")
    )
    add_notes_to_transaction = models.BooleanField(
        default=True, verbose_name=_("Add notes to transactions")
    )

    all_objects = models.Manager()  # Unfiltered manager
    objects = GenericAccountOwnerManager()  # Default filtered manager

    class Meta:
        verbose_name = _("Recurring Transaction")
        verbose_name_plural = _("Recurring Transactions")
        db_table = "recurring_transactions"

    def __str__(self):
        return self.description

    def save(self, *args, **kwargs):
        if not self.reference_date:
            self.reference_date = self.start_date

        instance = super().save(*args, **kwargs)
        return instance

    def create_upcoming_transactions(self, first_transaction=None):
        current_date = self.start_date
        reference_date = self.reference_date
        end_date = min(
            self.end_date
            or timezone.now().date()
            + (self.get_recurrence_delta() * self.keep_at_most),
            timezone.now().date() + (self.get_recurrence_delta() * self.keep_at_most),
        )

        # When converting an existing transaction, it becomes the first occurrence
        if first_transaction:
            self.adopt_transaction(first_transaction, current_date, reference_date)
            current_date = self.get_next_date(current_date)
            reference_date = self.get_next_date(reference_date)

        while current_date <= end_date:
            self.create_transaction(current_date, reference_date)
            current_date = self.get_next_date(current_date)
            reference_date = self.get_next_date(reference_date)

        self.last_generated_date = current_date - self.get_recurrence_delta()
        self.last_generated_reference_date = (
            reference_date - self.get_recurrence_delta()
        )
        self.save(
            update_fields=["last_generated_date", "last_generated_reference_date"]
        )

    def create_transaction(self, date, reference_date):
        created_transaction = Transaction.all_objects.create(
            account=self.account,
            type=self.transaction_type,
            date=date,
            reference_date=reference_date.replace(day=1),
            amount=self.amount,
            description=(
                self.description if self.add_description_to_transaction else ""
            ),
            category=self.category,
            is_paid=False,
            recurring_transaction=self,
            notes=self.notes if self.add_notes_to_transaction else "",
            owner=self.account.owner,
        )
        # Unfiltered managers: generation also runs without a current user, or with a
        # different one, and the scoped default manager would hide private rows.
        created_transaction.tags.set(self.tags(manager="all_objects").all())
        created_transaction.entities.set(self.entities(manager="all_objects").all())
        created_transaction.copy_sub_transactions_from(self)
        self.complete_transfer(created_transaction)

    def adopt_transaction(self, existing_transaction, date, reference_date):
        self._apply_to(
            existing_transaction,
            self.account,
            self.transaction_type,
            self.amount,
            date,
            reference_date,
        )
        if not self.is_transfer:
            return
        if existing_transaction.linked_transaction_id:
            # Converting a transfer: its "to" side joins the recurrence too
            self._apply_to(
                existing_transaction.linked_transaction,
                self.to_account,
                Transaction.Type.INCOME,
                self.to_amount or self.amount,
                date,
                reference_date,
            )
        else:
            self.complete_transfer(existing_transaction)

    def _apply_to(self, existing_transaction, account, type, amount, date, reference_date):
        existing_transaction.account = account
        existing_transaction.type = type
        existing_transaction.date = date
        existing_transaction.reference_date = reference_date.replace(day=1)
        existing_transaction.description = (
            self.description if self.add_description_to_transaction else ""
        )
        existing_transaction.category = self.category
        existing_transaction.notes = self.notes if self.add_notes_to_transaction else ""
        existing_transaction.recurring_transaction = self
        existing_transaction.amount = amount

        existing_transaction.save()
        existing_transaction.tags.set(self.tags(manager="all_objects").all())
        existing_transaction.entities.set(self.entities(manager="all_objects").all())
        existing_transaction.copy_sub_transactions_from(self)

    def get_recurrence_delta(self):
        if self.recurrence_type == self.RecurrenceType.DAY:
            return relativedelta(days=self.recurrence_interval)
        elif self.recurrence_type == self.RecurrenceType.WEEK:
            return relativedelta(weeks=self.recurrence_interval)
        elif self.recurrence_type == self.RecurrenceType.MONTH:
            return relativedelta(months=self.recurrence_interval)
        elif self.recurrence_type == self.RecurrenceType.YEAR:
            return relativedelta(years=self.recurrence_interval)

    def get_next_date(self, current_date):
        next_date = current_date + self.get_recurrence_delta()

        # A start on the 29th-31st is clamped in shorter months; return to that day
        # afterwards instead of keeping the clamped one.
        if (
            self.recurrence_type
            in (self.RecurrenceType.MONTH, self.RecurrenceType.YEAR)
            and self.start_date.day > current_date.day
            and current_date.day
            == calendar.monthrange(current_date.year, current_date.month)[1]
        ):
            last_day = calendar.monthrange(next_date.year, next_date.month)[1]
            next_date = next_date.replace(day=min(self.start_date.day, last_day))

        return next_date

    @classmethod
    def generate_upcoming_transactions(cls):
        today = timezone.now().date()
        recurring_transactions = cls.all_objects.filter(
            Q(models.Q(end_date__isnull=True) | Q(end_date__gte=today))
            & Q(is_paused=False)
        )

        for recurring_transaction in recurring_transactions:
            logger.info(
                f"Processing recurring transaction: {recurring_transaction.description}..."
            )

            if recurring_transaction.last_generated_date:
                start_date = recurring_transaction.get_next_date(
                    recurring_transaction.last_generated_date
                )
                reference_date = recurring_transaction.get_next_date(
                    recurring_transaction.last_generated_reference_date
                )
            else:
                start_date = max(recurring_transaction.start_date, today)
                reference_date = recurring_transaction.reference_date

            current_date = start_date
            end_date = min(
                recurring_transaction.end_date
                or today
                + (
                    recurring_transaction.get_recurrence_delta()
                    * recurring_transaction.keep_at_most
                ),
                today
                + (
                    recurring_transaction.get_recurrence_delta()
                    * recurring_transaction.keep_at_most
                ),
            )

            logger.info(f"End date: {end_date}")

            while current_date <= end_date:
                logger.info(f"Creating transaction for date: {current_date}")
                recurring_transaction.create_transaction(current_date, reference_date)
                current_date = recurring_transaction.get_next_date(current_date)
                reference_date = recurring_transaction.get_next_date(reference_date)

            recurring_transaction.last_generated_date = (
                current_date - recurring_transaction.get_recurrence_delta()
            )
            recurring_transaction.last_generated_reference_date = (
                reference_date - recurring_transaction.get_recurrence_delta()
            )
            recurring_transaction.save(
                update_fields=["last_generated_date", "last_generated_reference_date"]
            )

    def update_unpaid_transactions(self):
        """
        Updates all unpaid transactions associated with this RecurringTransaction.

        Only unpaid transactions (`is_paid=False`) are modified. Updates fields like
        amount, description, category, notes, and many-to-many relationships (tags, entities).
        """
        unpaid_transactions = self.transactions.filter(is_paid=False)

        for existing_transaction in unpaid_transactions:
            # Update fields based on RecurringTransaction
            is_to_side = (
                existing_transaction.linked_transaction_id
                and existing_transaction.type == Transaction.Type.INCOME
            )
            existing_transaction.amount = (
                self.to_amount or self.amount if is_to_side else self.amount
            )
            existing_transaction.description = (
                self.description if self.add_description_to_transaction else ""
            )
            existing_transaction.category = self.category
            existing_transaction.notes = (
                self.notes if self.add_notes_to_transaction else ""
            )

            # Update many-to-many relationships (see create_transaction)
            existing_transaction.tags.set(self.tags(manager="all_objects").all())
            existing_transaction.entities.set(
                self.entities(manager="all_objects").all()
            )

            existing_transaction.copy_sub_transactions_from(self)

            # Save updated transaction
            existing_transaction.save()

    def delete_unpaid_transactions(self):
        """
        Deletes all unpaid transactions associated with this RecurringTransaction.
        """
        today = timezone.localdate(timezone.now())
        self.transactions.filter(is_paid=False, date__gt=today).delete()


class QuickTransaction(TransferTemplate, OwnedObject):
    class Type(models.TextChoices):
        INCOME = "IN", _("Income")
        TRANSFER = "TR", _("Transfer")
        EXPENSE = "EX", _("Expense")

    name = models.CharField(
        max_length=100,
        null=False,
        blank=False,
        verbose_name=_("Name"),
    )

    account = models.ForeignKey(
        "accounts.Account",
        on_delete=models.CASCADE,
        verbose_name=_("Account"),
        related_name="quick_transactions",
    )
    type = models.CharField(
        max_length=2,
        choices=Type,
        default=Type.EXPENSE,
        verbose_name=_("Type"),
    )
    is_paid = models.BooleanField(default=True, verbose_name=_("Paid"))
    mute = models.BooleanField(default=False, verbose_name=_("Mute"))

    amount = models.DecimalField(
        max_digits=42,
        decimal_places=30,
        verbose_name=_("Amount"),
        validators=[validate_non_negative, validate_decimal_places],
    )

    description = models.CharField(
        max_length=500, verbose_name=_("Description"), blank=True
    )
    notes = models.TextField(blank=True, verbose_name=_("Notes"))
    category = models.ForeignKey(
        TransactionCategory,
        on_delete=models.SET_NULL,
        verbose_name=_("Category"),
        blank=True,
        null=True,
    )
    tags = models.ManyToManyField(
        TransactionTag,
        verbose_name=_("Tags"),
        blank=True,
    )
    entities = models.ManyToManyField(
        TransactionEntity,
        verbose_name=_("Entities"),
        blank=True,
        related_name="quick_transactions",
    )

    internal_note = models.TextField(blank=True, verbose_name=_("Internal Note"))
    internal_id = models.TextField(
        blank=True, null=True, unique=True, verbose_name=_("Internal ID")
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = OwnedObjectManager()
    all_objects = models.Manager()  # Unfiltered manager

    class Meta:
        verbose_name = _("Quick Transaction")
        verbose_name_plural = _("Quick Transactions")
        unique_together = ("name", "owner")
        db_table = "quick_transactions"
        default_manager_name = "objects"

    def save(self, *args, **kwargs):
        self.amount = truncate_decimal(
            value=self.amount, decimal_places=self.account.currency.decimal_places
        )

        self.full_clean()
        super().save(*args, **kwargs)

    def create_transaction(self):
        """Creates today's transaction from this template, and the "to" side when
        it's a transfer (None otherwise). Callers send the created signals."""
        today = timezone.localdate(timezone.now())
        new_transaction = Transaction(
            account=self.account,
            type=self.transaction_type,
            is_paid=self.is_paid,
            mute=self.mute,
            amount=self.amount,
            description=self.description,
            notes=self.notes,
            category=self.category,
            internal_note=self.internal_note,
            date=today,
            reference_date=today.replace(day=1),
        )
        with transaction.atomic():
            new_transaction.save()
            new_transaction.tags.set(self.tags.all())
            new_transaction.entities.set(self.entities.all())
            new_transaction.copy_sub_transactions_from(self)
            to_transaction = self.complete_transfer(new_transaction)
        return new_transaction, to_transaction

    def __str__(self):
        return self.name
