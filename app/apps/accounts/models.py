from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.middleware.thread_local import get_current_user
from apps.common.models import SharedObject, SharedObjectManager
from apps.transactions.models import Transaction


class AccountGroup(SharedObject):
    name = models.CharField(max_length=255, verbose_name=_("Name"))

    objects = SharedObjectManager()
    all_objects = models.Manager()  # Unfiltered manager

    class Meta:
        verbose_name = _("Account Group")
        verbose_name_plural = _("Account Groups")
        db_table = "account_groups"
        unique_together = (("owner", "name"),)
        ordering = ["name", "id"]

    def __str__(self):
        return self.name


class Account(SharedObject):
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
    is_investment = models.BooleanField(
        default=False,
        verbose_name=_("Investment"),
        help_text=_(
            "Show this account in the Investments tracker. Set an exchange currency to "
            "price it by units (stocks, ETFs, crypto); leave it empty to track it by "
            "value (fixed income, property, pensions)."
        ),
    )
    income_entities = models.ManyToManyField(
        "transactions.TransactionEntity",
        blank=True,
        related_name="investment_accounts",
        verbose_name=_("Income entities"),
        help_text=_(
            "Transactions with any of these entities count towards this investment's "
            "return: in this account, and income paid into other accounts (dividends, "
            "rent)."
        ),
    )
    income_categories = models.ManyToManyField(
        "transactions.TransactionCategory",
        blank=True,
        related_name="investment_accounts",
        verbose_name=_("Income categories"),
        help_text=_(
            "Transactions in this account with any of these categories are its result "
            "(interest, taxes, fees). On accounts tracked by value, everything else "
            "that isn't a transfer counts as money coming in or going out."
        ),
    )
    income_tags = models.ManyToManyField(
        "transactions.TransactionTag",
        blank=True,
        related_name="investment_accounts",
        verbose_name=_("Income tags"),
        help_text=_(
            "Same as income categories, for transactions with any of these tags."
        ),
    )
    is_archived = models.BooleanField(
        default=False,
        verbose_name=_("Archived"),
        help_text=_("Archived accounts don't show up nor count towards your net worth"),
    )
    untracked_by = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="untracked_accounts",
    )

    objects = SharedObjectManager()
    all_objects = models.Manager()  # Unfiltered manager

    class Meta:
        verbose_name = _("Account")
        verbose_name_plural = _("Accounts")
        unique_together = (("owner", "name"),)
        ordering = ["name", "id"]

    def __str__(self):
        return self.name

    def is_untracked_by(self):
        user = get_current_user()
        return self.untracked_by.filter(pk=user.pk).exists()

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
