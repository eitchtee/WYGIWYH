import logging
from typing import Set

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class Currency(models.Model):
    code = models.CharField(
        max_length=255, unique=False, verbose_name=_("Currency Code")
    )
    name = models.CharField(max_length=50, verbose_name=_("Currency Name"), unique=True)
    decimal_places = models.PositiveIntegerField(
        default=2,
        validators=[MaxValueValidator(30), MinValueValidator(0)],
        verbose_name=_("Decimal Places"),
    )
    prefix = models.CharField(max_length=10, verbose_name=_("Prefix"), blank=True)
    suffix = models.CharField(max_length=10, verbose_name=_("Suffix"), blank=True)

    exchange_currency = models.ForeignKey(
        "self",
        verbose_name=_("Exchange Currency"),
        on_delete=models.SET_NULL,
        related_name="exchange_currencies",
        null=True,
        blank=True,
        help_text=_("Default currency for exchange calculations"),
    )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _("Currency")
        verbose_name_plural = _("Currencies")

    def clean(self):
        super().clean()
        if self.exchange_currency == self:
            raise ValidationError(
                {
                    "exchange_currency": _(
                        "Currency cannot have itself as exchange currency."
                    )
                }
            )


class ExchangeRate(models.Model):
    from_currency = models.ForeignKey(
        Currency,
        on_delete=models.CASCADE,
        related_name="from_exchange_rates",
        verbose_name=_("From Currency"),
    )
    to_currency = models.ForeignKey(
        Currency,
        on_delete=models.CASCADE,
        related_name="to_exchange_rates",
        verbose_name=_("To Currency"),
    )
    rate = models.DecimalField(
        max_digits=42, decimal_places=30, verbose_name=_("Exchange Rate")
    )
    date = models.DateTimeField(verbose_name=_("Date and Time"))

    class Meta:
        verbose_name = _("Exchange Rate")
        verbose_name_plural = _("Exchange Rates")
        unique_together = ("from_currency", "to_currency", "date")

    def __str__(self):
        return f"{self.from_currency.code} to {self.to_currency.code} on {self.date}"

    def clean(self):
        super().clean()
        # Check if the attributes exist before comparing them
        if hasattr(self, "from_currency") and hasattr(self, "to_currency"):
            if self.from_currency == self.to_currency:
                raise ValidationError(
                    {"to_currency": _("From and To currencies cannot be the same.")}
                )


class ExchangeRateService(models.Model):
    """Configuration for exchange rate services"""

    class ServiceType(models.TextChoices):
        SYNTH_FINANCE = "synth_finance", "Synth Finance"
        SYNTH_FINANCE_STOCK = "synth_finance_stock", "Synth Finance Stock"
        COINGECKO_FREE = "coingecko_free", "CoinGecko (Demo/Free)"
        COINGECKO_PRO = "coingecko_pro", "CoinGecko (Pro)"
        TRANSITIVE = "transitive", "Transitive (Calculated from Existing Rates)"

    class IntervalType(models.TextChoices):
        ON = "on", _("On")
        EVERY = "every", _("Every X hours")
        NOT_ON = "not_on", _("Not on")

    name = models.CharField(max_length=255, unique=True, verbose_name=_("Service Name"))
    service_type = models.CharField(
        max_length=255, choices=ServiceType.choices, verbose_name=_("Service Type")
    )
    is_active = models.BooleanField(default=True, verbose_name=_("Active"))
    api_key = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name=_("API Key"),
        help_text=_("API key for the service (if required)"),
    )
    interval_type = models.CharField(
        max_length=255,
        choices=IntervalType.choices,
        verbose_name=_("Interval Type"),
        default=IntervalType.EVERY,
    )
    fetch_interval = models.CharField(
        max_length=1000, verbose_name=_("Interval"), default="24"
    )
    last_fetch = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Last Successful Fetch")
    )

    target_currencies = models.ManyToManyField(
        Currency,
        verbose_name=_("Target Currencies"),
        help_text=_(
            "Select currencies to fetch exchange rates for. Rates will be fetched for each currency against their set exchange currency."
        ),
        related_name="exchange_services",
        blank=True,
    )

    target_accounts = models.ManyToManyField(
        "accounts.Account",
        verbose_name=_("Target Accounts"),
        help_text=_(
            "Select accounts to fetch exchange rates for. Rates will be fetched for each account's currency against their set exchange currency."
        ),
        related_name="exchange_services",
        blank=True,
    )

    class Meta:
        verbose_name = _("Exchange Rate Service")
        verbose_name_plural = _("Exchange Rate Services")
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_provider(self):
        from apps.currencies.exchange_rates.fetcher import PROVIDER_MAPPING

        provider_class = PROVIDER_MAPPING[self.service_type]
        return provider_class(self.api_key)

    @staticmethod
    def _parse_hour_ranges(interval_str: str) -> Set[int]:
        """
        Parse hour ranges and individual hours from string.

        Valid formats:
        - Single hours: "1,5,9"
        - Ranges: "1-5"
        - Mixed: "1-5,8,10-12"

        Returns set of hours.
        """
        hours = set()

        for part in interval_str.strip().split(","):
            part = part.strip()
            if "-" in part:
                start, end = part.split("-")
                start, end = int(start), int(end)
                if not (0 <= start <= 23 and 0 <= end <= 23):
                    raise ValueError("Hours must be between 0 and 23")
                if start > end:
                    raise ValueError(f"Invalid range: {start}-{end}")
                hours.update(range(start, end + 1))
            else:
                hour = int(part)
                if not 0 <= hour <= 23:
                    raise ValueError("Hours must be between 0 and 23")
                hours.add(hour)

        return hours

    def clean(self):
        super().clean()
        try:
            if self.interval_type == self.IntervalType.EVERY:
                if not self.fetch_interval.isdigit():
                    raise ValidationError(
                        {
                            "fetch_interval": _(
                                "'Every X hours' interval type requires a positive integer."
                            )
                        }
                    )
                hours = int(self.fetch_interval)
                if hours < 0 or hours > 23:
                    raise ValidationError(
                        {
                            "fetch_interval": _(
                                "'Every X hours' interval must be between 0 and 23."
                            )
                        }
                    )
            else:
                try:
                    # Parse and validate hour ranges
                    hours = self._parse_hour_ranges(self.fetch_interval)
                    # Store in normalized format (optional)
                    self.fetch_interval = ",".join(str(h) for h in sorted(hours))
                except ValueError as e:
                    raise ValidationError(
                        {
                            "fetch_interval": _(
                                "Invalid hour format. Use comma-separated hours (0-23) "
                                "and/or ranges (e.g., '1-5,8,10-12')."
                            )
                        }
                    )
        except ValidationError:
            raise
        except Exception as e:
            raise ValidationError(
                {
                    "fetch_interval": _(
                        "Invalid format. Please check the requirements for your selected interval type."
                    )
                }
            )
