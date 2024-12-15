import logging

from dateutil.relativedelta import relativedelta
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.fields.month_year import MonthYearModelField
from apps.common.functions.decimals import truncate_decimal
from apps.currencies.utils.convert import convert
from apps.transactions.validators import validate_decimal_places, validate_non_negative

logger = logging.getLogger()


class TransactionCategory(models.Model):
    name = models.CharField(max_length=255, verbose_name=_("Name"), unique=True)
    mute = models.BooleanField(default=False, verbose_name=_("Mute"))

    class Meta:
        verbose_name = _("Transaction Category")
        verbose_name_plural = _("Transaction Categories")
        db_table = "t_categories"

    def __str__(self):
        return self.name


class TransactionTag(models.Model):
    name = models.CharField(max_length=255, verbose_name=_("Name"), unique=True)

    class Meta:
        verbose_name = _("Transaction Tags")
        verbose_name_plural = _("Transaction Tags")
        db_table = "tags"

    def __str__(self):
        return self.name


class TransactionEntity(models.Model):
    name = models.CharField(max_length=255, verbose_name=_("Name"))

    # Add any other fields you might want for entities

    class Meta:
        verbose_name = _("Entity")
        verbose_name_plural = _("Entities")
        db_table = "entities"

    def __str__(self):
        return self.name


class Transaction(models.Model):
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

    description = models.CharField(max_length=500, verbose_name=_("Description"))
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

    class Meta:
        verbose_name = _("Transaction")
        verbose_name_plural = _("Transactions")
        db_table = "transactions"

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

        return None


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
            new_transaction = Transaction.objects.create(
                account=self.account,
                type=self.type,
                date=transaction_date,
                is_paid=False,
                reference_date=transaction_reference_date,
                amount=self.installment_amount,
                description=self.description,
                category=self.category,
                installment_plan=self,
                installment_id=i,
                notes=self.notes,
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
                existing_transaction.amount = self.installment_amount
                existing_transaction.description = self.description
                existing_transaction.category = self.category
                existing_transaction.notes = self.notes
                existing_transaction.save()

                # Update tags
                existing_transaction.tags.set(self.tags.all())
                existing_transaction.entities.set(self.entities.all())
            else:
                # If the transaction doesn't exist, create a new one
                new_transaction = Transaction.objects.create(
                    account=self.account,
                    type=self.type,
                    date=transaction_date,
                    is_paid=False,
                    reference_date=transaction_reference_date,
                    amount=self.installment_amount,
                    description=self.description,
                    category=self.category,
                    installment_plan=self,
                    installment_id=i,
                    notes=self.notes,
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
        created_transaction = Transaction.objects.create(
            account=self.account,
            type=self.type,
            date=date,
            reference_date=reference_date.replace(day=1),
            amount=self.amount,
            description=self.description,
            category=self.category,
            is_paid=False,
            recurring_transaction=self,
            notes=self.notes,
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
