import logging
from datetime import timedelta

from django.db.models import QuerySet
from django.utils import timezone

from apps.currencies.exchange_rates.providers import (
    SynthFinanceProvider,
    CoinGeckoFreeProvider,
    CoinGeckoProProvider,
)
from apps.currencies.models import ExchangeRateService, ExchangeRate, Currency

logger = logging.getLogger(__name__)


# Map service types to provider classes
PROVIDER_MAPPING = {
    "synth_finance": SynthFinanceProvider,
    "coingecko_free": CoinGeckoFreeProvider,
    "coingecko_pro": CoinGeckoProProvider,
}


class ExchangeRateFetcher:
    @staticmethod
    def fetch_due_rates(force: bool = False) -> None:
        """
        Fetch rates for all services that are due for update.

        Args:
            force (bool): If True, fetches all active services regardless of their last fetch time.
                         If False, only fetches services that are due according to their interval.
        """
        services = ExchangeRateService.objects.filter(is_active=True)
        current_time = timezone.now().replace(minute=0, second=0, microsecond=0)

        for service in services:
            try:
                if force:
                    logger.info(f"Force fetching rates for {service.name}")
                    ExchangeRateFetcher._fetch_service_rates(service)
                    continue

                # Regular schedule-based fetching
                if service.last_fetch is None:
                    logger.info(f"First fetch for service: {service.name}")
                    ExchangeRateFetcher._fetch_service_rates(service)
                    continue

                # Calculate when the next fetch should occur
                next_fetch_due = (
                    service.last_fetch + timedelta(hours=service.fetch_interval_hours)
                ).replace(minute=0, second=0, microsecond=0)

                # Check if it's time for the next fetch
                if current_time >= next_fetch_due:
                    logger.info(
                        f"Fetching rates for {service.name}. "
                        f"Last fetch: {service.last_fetch}, "
                        f"Interval: {service.fetch_interval_hours}h"
                    )
                    ExchangeRateFetcher._fetch_service_rates(service)
                else:
                    logger.debug(
                        f"Skipping {service.name}. "
                        f"Next fetch due at: {next_fetch_due}"
                    )

            except Exception as e:
                logger.error(f"Error checking fetch schedule for {service.name}: {e}")

    @staticmethod
    def _get_unique_currency_pairs(
        service: ExchangeRateService,
    ) -> tuple[QuerySet, set]:
        """
        Get unique currency pairs from both target_currencies and target_accounts
        Returns a tuple of (target_currencies QuerySet, exchange_currencies set)
        """
        # Get currencies from target_currencies
        target_currencies = set(service.target_currencies.all())

        # Add currencies from target_accounts
        for account in service.target_accounts.all():
            if account.currency and account.exchange_currency:
                target_currencies.add(account.currency)

        # Convert back to QuerySet for compatibility with existing code
        target_currencies_qs = Currency.objects.filter(
            id__in=[curr.id for curr in target_currencies]
        )

        # Get unique exchange currencies
        exchange_currencies = set()

        # From target_currencies
        for currency in target_currencies:
            if currency.exchange_currency:
                exchange_currencies.add(currency.exchange_currency)

        # From target_accounts
        for account in service.target_accounts.all():
            if account.exchange_currency:
                exchange_currencies.add(account.exchange_currency)

        return target_currencies_qs, exchange_currencies

    @staticmethod
    def _fetch_service_rates(service: ExchangeRateService) -> None:
        """Fetch rates for a specific service"""
        try:
            provider = service.get_provider()

            # Check if API key is required but missing
            if provider.requires_api_key() and not service.api_key:
                logger.error(f"API key required but not provided for {service.name}")
                return

            # Get unique currency pairs from both sources
            target_currencies, exchange_currencies = (
                ExchangeRateFetcher._get_unique_currency_pairs(service)
            )

            # Skip if no currencies to process
            if not target_currencies or not exchange_currencies:
                logger.info(f"No currency pairs to process for service {service.name}")
                return

            rates = provider.get_rates(target_currencies, exchange_currencies)

            # Track processed currency pairs to avoid duplicates
            processed_pairs = set()

            for from_currency, to_currency, rate in rates:
                # Create a unique identifier for this currency pair
                pair_key = (from_currency.id, to_currency.id)
                if pair_key in processed_pairs:
                    continue

                if provider.rates_inverted:
                    # If rates are inverted, we need to swap currencies
                    ExchangeRate.objects.create(
                        from_currency=to_currency,
                        to_currency=from_currency,
                        rate=rate,
                        date=timezone.now(),
                    )
                    processed_pairs.add((to_currency.id, from_currency.id))
                else:
                    # If rates are not inverted, we can use them as is
                    ExchangeRate.objects.create(
                        from_currency=from_currency,
                        to_currency=to_currency,
                        rate=rate,
                        date=timezone.now(),
                    )
                    processed_pairs.add((from_currency.id, to_currency.id))

            service.last_fetch = timezone.now()
            service.save()

        except Exception as e:
            logger.error(f"Error fetching rates for {service.name}: {e}")
