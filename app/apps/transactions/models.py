import logging

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import Q
from django.dispatch import Signal
from django.template.defaultfilters import date
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.fields.month_year import MonthYearModelField
from apps.common.functions.decimals import truncate_decimal
from apps.common.templatetags.decimal import localize_number, drop_trailing_zeros
from apps.currencies.utils.convert import convert
from apps.transactions.validators import validate_decimal_places, validate_non_negative
from apps.common.middleware.thread_local import get_current_user
from apps.common.models import SharedObject, SharedObjectManager, OwnedObject

logger = logging.getLogger()


transaction_created = Signal()
transaction_updated = Signal()
transaction_deleted = Signal()


class SoftDeleteQuerySet(models.QuerySet):
    @staticmethod
    def _emit_signals(instances, created=False):
        """Helper to emit signals for multiple instances"""
        for instance in instances:
            if created:
                transaction_created.send(sender=instance)
            else:
                transaction_updated.send(sender=instance)

    def bulk_create(self, objs, emit_signal=True, **kwargs):
        instances = super().bulk_create(objs, **kwargs)

        if emit_signal:
            self._emit_signals(instances, created=True)

        return instances

    def bulk_update(self, objs, fields, emit_signal=True, **kwargs):
        result = super().bulk_update(objs, fields, **kwargs)

        if emit_signal:
            self._emit_signals(objs, created=False)

        return result

    def update(self, emit_signal=True, **kwargs):
        # Get instances before update
        instances = list(self)
        result = super().update(**kwargs)

        if emit_signal:
            # Refresh instances to get new values
            refreshed = self.model.objects.filter(pk__in=[obj.pk for obj in instances])
            self._emit_signals(refreshed, created=False)

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


class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        qs = SoftDeleteQuerySet(self.model, using=self._db)
        user = get_current_user()
        if user and not user.is_anonymous:
            return qs.filter(
                Q(account__visibility="public")
                | Q(account__owner=user)
                | Q(account__shared_with=user)
                | Q(account__visibility="private", account__owner=None),
                deleted=False,
            ).distinct()
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

    def save(self, *args, **kwargs):
        self.amount = truncate_decimal(
            value=self.amount, decimal_places=self.account.currency.decimal_places
        )

        if self.reference_date:
            self.reference_date = self.reference_date.replace(day=1)
        elif not self.reference_date and self.date:
            self.reference_date = self.date.replace(day=1)

        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
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

    def exchanged_amount(self):
        if self.account.exchange_currency:
            converted_amount, prefix, suffix, decimal_places = convert(
                self.amount,
                to_currency=self.account.exchange_currency,
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
        elif self.account.currency.exchange_currency:
            converted_amount, prefix, suffix, decimal_places = convert(
                self.amount,
                to_currency=self.account.currency.exchange_currency,
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
        tags = ", ".join([x.name for x in self.tags.all()]) or _("No tags")
        category = self.category or _("No category")
        amount = localize_number(drop_trailing_zeros(self.amount))
        description = self.description or _("No description")
        return f"[{frmt_date}][{type_display}][{account}] {description} • {category} • {tags} • {amount}"


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
            )
            new_transaction.tags.set(self.tags.all())
            new_transaction.entities.set(self.entities.all())

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
                )
                new_transaction.tags.set(self.tags.all())
                new_transaction.entities.set(self.entities.all())

        # Remove any extra transactions that are no longer part of the plan
        self.transactions.filter(
            Q(installment_id__gt=self.installment_total_number)
            | Q(installment_id__lt=self.installment_start)
        ).delete()

    def delete(self, *args, **kwargs):
        # Delete related transactions
        self.transactions.all().delete()
        super().delete(*args, **kwargs)


class RecurringTransaction(models.Model):
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
        choices=Transaction.Type,
        default=Transaction.Type.EXPENSE,
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

    def create_upcoming_transactions(self):
        current_date = self.start_date
        reference_date = self.reference_date
        end_date = min(
            self.end_date or timezone.now().date() + (self.get_recurrence_delta() * 5),
            timezone.now().date() + (self.get_recurrence_delta() * 5),
        )

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
            type=self.type,
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
        )
        if self.tags.exists():
            created_transaction.tags.set(self.tags.all())
        if self.entities.exists():
            created_transaction.entities.set(self.entities.all())

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
        return current_date + self.get_recurrence_delta()

    @classmethod
    def generate_upcoming_transactions(cls):
        today = timezone.now().date()
        recurring_transactions = cls.objects.filter(
            Q(models.Q(end_date__isnull=True) | Q(end_date__gte=today))
            & Q(is_paused=False)
        )

        for recurring_transaction in recurring_transactions:
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
                or today + (recurring_transaction.get_recurrence_delta() * 6),
                today + (recurring_transaction.get_recurrence_delta() * 6),
            )

            while current_date <= end_date:
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
            existing_transaction.amount = self.amount
            existing_transaction.description = (
                self.description if self.add_description_to_transaction else ""
            )
            existing_transaction.category = self.category
            existing_transaction.notes = (
                self.notes if self.add_notes_to_transaction else ""
            )

            # Update many-to-many relationships
            existing_transaction.tags.set(self.tags.all())
            existing_transaction.entities.set(self.entities.all())

            # Save updated transaction
            existing_transaction.save()

    def delete_unpaid_transactions(self):
        """
        Deletes all unpaid transactions associated with this RecurringTransaction.
        """
        today = timezone.localdate(timezone.now())
        self.transactions.filter(is_paid=False, date__gt=today).delete()
