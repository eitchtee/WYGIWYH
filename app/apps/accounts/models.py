from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.transactions.models import Transaction


class AccountGroup(models.Model):
    name = models.CharField(max_length=255, verbose_name=_("Name"), unique=True)

    class Meta:
        verbose_name = _("Account Group")
        verbose_name_plural = _("Account Groups")
        db_table = "account_groups"

    def __str__(self):
        return self.name


class Account(models.Model):
    name = models.CharField(max_length=255, verbose_name=_("Name"))
    group = models.ForeignKey(
        AccountGroup,
        on_delete=models.SET_NULL,
        verbose_name=_("Account Group"),
        blank=True,
        null=True,
    )
    currency = models.ForeignKey(
        "currencies.Currency",
        verbose_name=_("Currency"),
        on_delete=models.PROTECT,
        related_name="accounts",
    )
    exchange_currency = models.ForeignKey(
        "currencies.Currency",
        verbose_name=_("Exchange Currency"),
        on_delete=models.SET_NULL,
        related_name="exchange_accounts",
        null=True,
        blank=True,
        help_text=_("Default currency for exchange calculations"),
    )

    is_asset = models.BooleanField(
        default=False,
        verbose_name=_("Asset account"),
        help_text=_(
            "Asset accounts count towards your Net Worth, but not towards your month."
        ),
    )
    is_archived = models.BooleanField(
        default=False,
        verbose_name=_("Archived"),
        help_text=_("Archived accounts don't show up nor count towards your net worth"),
    )

    class Meta:
        verbose_name = _("Account")
        verbose_name_plural = _("Accounts")

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.exchange_currency == self.currency:
            raise ValidationError(
                {
                    "exchange_currency": _(
                        "Exchange currency cannot be the same as the account's main currency."
                    )
                }
            )
