from dateutil.relativedelta import relativedelta
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from apps.common.functions.decimals import truncate_decimal
from apps.transactions.validators import validate_decimal_places, validate_non_negative
from apps.currencies.utils.convert import convert
from apps.common.fields.month_year import MonthYearModelField


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


class InstallmentPlan(models.Model):
    account = models.ForeignKey(
        "accounts.Account", on_delete=models.CASCADE, verbose_name=_("Account")
    )
    description = models.CharField(max_length=500, verbose_name=_("Description"))
    number_of_installments = models.PositiveIntegerField(
        validators=[MinValueValidator(1)], verbose_name=_("Number of Installments")
    )
    # start_date = models.DateField(verbose_name=_("Start Date"))
    # end_date = models.DateField(verbose_name=_("End Date"))

    class Meta:
        verbose_name = _("Installment Plan")
        verbose_name_plural = _("Installment Plans")

    def __str__(self):
        return f"{self.description} - {self.number_of_installments} installments"

    def delete(self, *args, **kwargs):
        # Delete related transactions
        self.transactions.all().delete()
        super().delete(*args, **kwargs)


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
        InstallmentPlan,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="transactions",
        verbose_name=_("Installment Plan"),
    )

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
