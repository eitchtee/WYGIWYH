from django.db import models
from django.utils.translation import gettext_lazy as _


class Account(models.Model):
    name = models.CharField(max_length=40, verbose_name=_("Name"))
    currency = models.ForeignKey(
        "currencies.Currency",
        verbose_name=_("Currency"),
        on_delete=models.PROTECT,
        related_name="accounts",
    )
    is_asset = models.BooleanField(
        default=False,
        verbose_name=_("Is an asset account?"),
        help_text=_(
            "Asset accounts count towards your Net Worth, but not towards your month."
        ),
    )
    a = models.BigIntegerField

    class Meta:
        verbose_name = _("Account")
        verbose_name_plural = _("Accounts")

    def __str__(self):
        return self.name
