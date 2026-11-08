from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import OwnedObject, OwnedObjectManager


class BankSyncService(OwnedObject):
    class ServiceType(models.TextChoices):
        LUNCHFLOW = "lunchflow", "Lunch Flow"
        SIMPLEFIN = "simplefin", "SimpleFIN"
        PLUGGY = "pluggy", "Pluggy"

    name = models.CharField(max_length=255, verbose_name=_("Name"))
    service_type = models.CharField(
        max_length=255, choices=ServiceType.choices, verbose_name=_("Service Type")
    )
    is_active = models.BooleanField(default=True, verbose_name=_("Active"))
    # Provider specific, keyed by the provider's settings_fields
    settings = models.JSONField(default=dict, blank=True, verbose_name=_("Settings"))
    sync_interval = models.PositiveIntegerField(
        default=24,
        validators=[MinValueValidator(1), MaxValueValidator(168)],
        verbose_name=_("Sync every X hours"),
        help_text=_("Most banks only update once a day."),
    )
    trigger_rules = models.BooleanField(
        default=True,
        verbose_name=_("Trigger transaction rules"),
        help_text=_("Run your transaction rules on synced transactions."),
    )
    match_existing = models.BooleanField(
        default=False,
        verbose_name=_("Match existing transactions"),
        help_text=_(
            "Instead of creating a synced transaction, link it to one you already "
            "added on the same account, with the same type and amount, dated up to "
            "3 days apart."
        ),
    )
    last_sync = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Last Successful Sync")
    )
    failure_count = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True, default="")

    objects = OwnedObjectManager()

    class Meta:
        verbose_name = _("Bank Sync Service")
        verbose_name_plural = _("Bank Sync Services")
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_provider(self):
        from apps.bank_sync.providers import PROVIDER_MAPPING

        return PROVIDER_MAPPING[self.service_type](self.settings)


class BankSyncAccount(models.Model):
    """An account on the provider, optionally linked to a WYGIWYH account."""

    service = models.ForeignKey(
        BankSyncService, on_delete=models.CASCADE, related_name="accounts"
    )
    external_id = models.CharField(max_length=255)
    external_name = models.CharField(max_length=255, blank=True)
    # Currencies seen on the provider, offered as choices for `currencies`
    available_currencies = models.JSONField(default=list, blank=True)
    currencies = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("Currencies"),
        help_text=_("Only sync transactions in these currencies. Empty syncs all."),
    )
    # Provider side problem, like an expired connection
    remote_error = models.TextField(blank=True, default="")
    last_error = models.TextField(blank=True, default="")

    account = models.ForeignKey(
        "accounts.Account",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bank_sync_accounts",
        verbose_name=_("Account"),
    )
    start_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Sync from"),
        help_text=_("Transactions before this date are never imported."),
    )
    last_synced_date = models.DateField(null=True, blank=True)

    class Meta:
        unique_together = ("service", "external_id")
        ordering = ["external_name"]

    def __str__(self):
        return self.external_name or self.external_id
