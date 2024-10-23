from django.db import models
from django.utils.translation import gettext_lazy as _


class TransactionRule(models.Model):
    active = models.BooleanField(default=True)
    on_update = models.BooleanField(default=False)
    on_create = models.BooleanField(default=True)
    name = models.CharField(max_length=100, verbose_name=_("Name"))
    description = models.TextField(blank=True, null=True, verbose_name=_("Description"))
    trigger = models.TextField(verbose_name=_("Trigger"))

    def __str__(self):
        return self.name


class TransactionRuleAction(models.Model):
    class Field(models.TextChoices):
        account = "account", _("Account")
        type = "type", _("Type")
        is_paid = "is_paid", _("Paid")
        date = "date", _("Date")
        reference_date = "reference_date", _("Reference Date")
        amount = "amount", _("Amount")
        description = "description", _("Description")
        notes = "notes", _("Notes")
        category = "category", _("Category")
        tags = "tags", _("Tags")

    rule = models.ForeignKey(
        TransactionRule,
        on_delete=models.CASCADE,
        related_name="actions",
        verbose_name=_("Rule"),
    )
    field = models.CharField(
        max_length=50,
        choices=Field,
        verbose_name=_("Field"),
    )
    value = models.TextField(verbose_name=_("Value"))

    def __str__(self):
        return f"{self.rule} - {self.field} - {self.value}"
