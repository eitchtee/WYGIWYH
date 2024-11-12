from decimal import Decimal

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.currencies.utils.convert import convert


class DCAStrategy(models.Model):
    name = models.CharField(max_length=255, verbose_name=_("Name"))
    target_currency = models.ForeignKey(
        "currencies.Currency",
        verbose_name=_("Target Currency"),
        on_delete=models.PROTECT,
        related_name="dca_target_strategies",
    )
    payment_currency = models.ForeignKey(
        "currencies.Currency",
        verbose_name=_("Payment Currency"),
        on_delete=models.PROTECT,
        related_name="dca_payment_strategies",
    )
    notes = models.TextField(blank=True, null=True, verbose_name=_("Notes"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("DCA Strategy")
        verbose_name_plural = _("DCA Strategies")
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    def total_invested(self):
        return sum(entry.amount_paid for entry in self.entries.all())

    def total_received(self):
        return sum(entry.amount_received for entry in self.entries.all())

    def average_entry_price(self):
        total_invested = self.total_invested()
        total_received = self.total_received()
        if total_received:
            return total_invested / total_received
        return Decimal("0")

    def total_entries(self):
        return self.entries.count()

    def current_total_value(self):
        """Calculate current total value of all entries"""
        return sum(entry.current_value() for entry in self.entries.all())

    def total_profit_loss(self):
        """Calculate total P/L in payment currency"""
        return self.current_total_value() - self.total_invested()

    def total_profit_loss_percentage(self):
        """Calculate total P/L percentage"""
        total_invested = self.total_invested()
        if total_invested:
            return (self.total_profit_loss() / total_invested) * 100
        return Decimal("0")


class DCAEntry(models.Model):
    strategy = models.ForeignKey(
        DCAStrategy,
        on_delete=models.CASCADE,
        related_name="entries",
        verbose_name=_("Strategy"),
    )
    date = models.DateField(verbose_name=_("Date"))
    amount_paid = models.DecimalField(
        max_digits=42, decimal_places=30, verbose_name=_("Amount Paid")
    )
    amount_received = models.DecimalField(
        max_digits=42, decimal_places=30, verbose_name=_("Amount Received")
    )
    expense_transaction = models.ForeignKey(
        "transactions.Transaction",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="dca_expense_entries",
        verbose_name=_("Expense Transaction"),
    )
    income_transaction = models.ForeignKey(
        "transactions.Transaction",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="dca_income_entries",
        verbose_name=_("Income Transaction"),
    )
    notes = models.TextField(blank=True, null=True, verbose_name=_("Notes"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("DCA Entry")
        verbose_name_plural = _("DCA Entries")
        ordering = ["-date"]

    def __str__(self):
        return f"{self.strategy.name} - {self.date}"

    def entry_price(self):
        if self.amount_received:
            return self.amount_paid / self.amount_received
        return 0

    def current_value(self):
        """
        Calculate current value of received amount in payment currency
        using latest exchange rate
        """
        if not self.amount_received:
            return Decimal("0")

        amount, _, _, _ = convert(
            self.amount_received,
            self.strategy.target_currency,
            self.strategy.payment_currency,
            timezone.now().date(),
        )

        return amount or Decimal("0")

    def profit_loss(self):
        """Calculate P/L in payment currency"""
        return self.current_value() - self.amount_paid

    def profit_loss_percentage(self):
        """Calculate P/L percentage"""
        if self.amount_paid:
            return (self.profit_loss() / self.amount_paid) * Decimal("100")
        return Decimal("0")
