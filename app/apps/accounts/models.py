from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
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
    is_archived = models.BooleanField(
        default=False,
        verbose_name=_("Archived"),
        help_text=_("Archived accounts don't show up nor count towards your net worth"),
    )
    is_default = models.BooleanField(
        default=False,
        verbose_name=_("Default"),
        help_text=_("Use as a default account when adding new transactions"),
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

        constraints = [
            models.UniqueConstraint(
                fields=["owner"],
                condition=models.Q(is_default=True),
                name="unique_default_account_per_owner",
            )
        ]

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

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.is_archived:
                self.is_default = False
            if self.is_default:
                Account.objects.filter(owner_id=self.owner_id, is_default=True).exclude(pk=self.pk).update(is_default=False)
            super().save(*args, **kwargs)
