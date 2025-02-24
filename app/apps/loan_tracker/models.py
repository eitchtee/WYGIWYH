from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.transactions.models import (
    TransactionEntity,
    TransactionCategory,
    TransactionTag,
)
from apps.transactions.validators import validate_non_negative


class Loan(models.Model):
    class Type(models.TextChoices):
        BORROWING = "EX", _("Borrowing")
        LENDING = "IN", _("Lending")

    type = models.CharField(
        max_length=2,
        choices=Type,
        default=Type.LENDING,
        verbose_name=_("Type"),
    )

    name = models.CharField(max_length=255, verbose_name=_("Name"))

    account = models.ForeignKey(
        "accounts.Account",
        on_delete=models.CASCADE,
        verbose_name=_("Account"),
        related_name="transactions",
    )
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
    entity = models.ForeignKey(
        TransactionEntity,
        on_delete=models.PROTECT,
        related_name="loans",
        verbose_name=_("Entity"),
    )

    notes = models.TextField(blank=True, verbose_name=_("Notes"))

    class Meta:
        verbose_name = _("Loan")
        verbose_name_plural = _("Loans")


class LoanCollateral(models.Model):
    loan = models.ForeignKey(
        Loan,
        on_delete=models.CASCADE,
        related_name="collaterals",
        verbose_name=_("Loan"),
    )
    description = models.CharField(max_length=255, verbose_name=_("Description"))
    value = models.DecimalField(
        max_digits=42,
        decimal_places=30,
        validators=[validate_non_negative],
        verbose_name=_("Value"),
    )
    notes = models.TextField(blank=True, verbose_name=_("Notes"))


class LoanPayment(models.Model):
    loan = models.ForeignKey(
        Loan, on_delete=models.CASCADE, verbose_name=_("Loan"), related_name="payments"
    )

    principal_amount = models.DecimalField(
        max_digits=42,
        decimal_places=30,
        validators=[validate_non_negative],
        verbose_name=_("Principal Amount"),
    )
    interest = models.DecimalField(
        max_digits=42,
        decimal_places=30,
        validators=[validate_non_negative],
        verbose_name=_("Interest"),
    )
    other = models.DecimalField(
        max_digits=42,
        decimal_places=30,
        validators=[validate_non_negative],
        verbose_name=_("Interest"),
    )

    transaction = models.ForeignKey(
        "transactions.Transaction",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="loan_payments",
        verbose_name=_("Transaction"),
    )

    class Meta:
        verbose_name = _("Loan Payment")
        verbose_name_plural = _("Loan Payments")
