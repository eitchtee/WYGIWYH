import logging

from dateutil.relativedelta import relativedelta
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.db.models import Q
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from apps.common.functions.decimals import truncate_decimal
from apps.transactions.validators import validate_decimal_places, validate_non_negative
from apps.currencies.utils.convert import convert
from apps.common.fields.month_year import MonthYearModelField

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


# class InstallmentPlan(models.Model):
#     account = models.ForeignKey(
#         "accounts.Account", on_delete=models.CASCADE, verbose_name=_("Account")
#     )
#     description = models.CharField(max_length=500, verbose_name=_("Description"))
#     number_of_installments = models.PositiveIntegerField(
#         validators=[MinValueValidator(1)], verbose_name=_("Number of Installments")
#     )
#     # start_date = models.DateField(verbose_name=_("Start Date"))
#     # end_date = models.DateField(verbose_name=_("End Date"))
#
#     class Meta:
#         verbose_name = _("Installment Plan")
#         verbose_name_plural = _("Installment Plans")
#
#     def __str__(self):
#         return f"{self.description} - {self.number_of_installments} installments"
#
#     def delete(self, *args, **kwargs):
#         # Delete related transactions
#         self.transactions.all().delete()
#         super().delete(*args, **kwargs)


class Transaction(models.Model):
    class Type(models.TextChoices):
        INCOME = "IN", _("Income")
        EXPENSE = "EX", _("Expense")

    account = models.ForeignKey(
        "accounts.Account", on_delete=models.CASCADE, verbose_name=_("Account")
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
    tags = models.ManyToManyField(TransactionTag, verbose_name=_("Tags"), blank=True)

    installment_plan = models.ForeignKey(
        "InstallmentPlan",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="transactions",
        verbose_name=_("Installment Plan"),
    )
    installment_id = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        verbose_name = _("Transaction")
        verbose_name_plural = _("Transactions")
        db_table = "transactions"

    def save(self, *args, **kwargs):
        self.amount = truncate_decimal(
            value=self.amount, decimal_places=self.account.currency.decimal_places
        )
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

    class Meta:
        verbose_name = _("Installment Plan")
        verbose_name_plural = _("Installment Plans")

    def __str__(self):
        return self.description

    def save(self, *args, **kwargs):
        if not self.reference_date:
            self.reference_date = self.start_date.replace(day=1)

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
            )
            new_transaction.tags.set(self.tags.all())

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
                existing_transaction.save()

                # Update tags
                existing_transaction.tags.set(self.tags.all())
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
                )
                new_transaction.tags.set(self.tags.all())

        # Remove any extra transactions that are no longer part of the plan
        self.transactions.filter(
            Q(installment_id__gt=self.installment_total_number)
            | Q(installment_id__lt=self.installment_start)
        ).delete()

    def delete(self, *args, **kwargs):
        # Delete related transactions
        self.transactions.all().delete()
        super().delete(*args, **kwargs)
