import logging
from datetime import timedelta

from django.db.models import QuerySet
from django.utils import timezone

import apps.currencies.exchange_rates.providers as providers
from apps.currencies.models import ExchangeRateService, ExchangeRate, Currency

logger = logging.getLogger(__name__)


# Map service types to provider classes
PROVIDER_MAPPING = {
    "synth_finance": providers.SynthFinanceProvider,
    "synth_finance_stock": providers.SynthFinanceStockProvider,
    "coingecko_free": providers.CoinGeckoFreeProvider,
    "coingecko_pro": providers.CoinGeckoProProvider,
    "transitive": providers.TransitiveRateProvider,
    "frankfurter": providers.FrankfurterProvider,
}


class ExchangeRateFetcher:
    def _should_fetch_at_hour(service: ExchangeRateService, current_hour: int) -> bool:
        """Check if service should fetch rates at given hour based on interval type."""
        try:
            if service.interval_type == ExchangeRateService.IntervalType.NOT_ON:
                blocked_hours = ExchangeRateService._parse_hour_ranges(
                    service.fetch_interval
                )
                should_fetch = current_hour not in blocked_hours
                logger.info(
                    f"NOT_ON check for {service.name}: "
                    f"current_hour={current_hour}, "
                    f"blocked_hours={blocked_hours}, "
                    f"should_fetch={should_fetch}"
                )
                return should_fetch

            if service.interval_type == ExchangeRateService.IntervalType.ON:
                allowed_hours = ExchangeRateService._parse_hour_ranges(
                    service.fetch_interval
                )

                should_fetch = current_hour in allowed_hours

                logger.info(
                    f"ON check for {service.name}: "
                    f"current_hour={current_hour}, "
                    f"allowed_hours={allowed_hours}, "
                    f"should_fetch={should_fetch}"
                )

                return should_fetch

            if service.interval_type == ExchangeRateService.IntervalType.EVERY:
                try:
                    interval_hours = int(service.fetch_interval)

                    if service.last_fetch is None:
                        return True

                    # Round down to nearest hour
                    now = timezone.now().replace(minute=0, second=0, microsecond=0)
                    last_fetch = service.last_fetch.replace(
                        minute=0, second=0, microsecond=0
                    )

                    hours_since_last = (now - last_fetch).total_seconds() / 3600
                    should_fetch = hours_since_last >= interval_hours

                    logger.info(
                        f"EVERY check for {service.name}: "
                        f"hours_since_last={hours_since_last:.1f}, "
                        f"interval={interval_hours}, "
                        f"should_fetch={should_fetch}"
                    )
                    return should_fetch
                except ValueError:
                    logger.error(
                        f"Invalid EVERY interval format for {service.name}: "
                        f"expected single number, got '{service.fetch_interval}'"
                    )
                    return False

            return False

        except ValueError as e:
            logger.error(f"Error parsing fetch_interval for {service.name}: {e}")
            return False

    @staticmethod
    def fetch_due_rates(force: bool = False) -> None:
        """
        Fetch rates for all services that are due for update.
        Args:
            force (bool): If True, fetches all active services regardless of their schedule.
        """
        services = ExchangeRateService.objects.filter(is_active=True)
        current_time = timezone.now().astimezone()
        current_hour = current_time.hour

        for service in services:
            try:
                if force:
                    logger.info(f"Force fetching rates for {service.name}")
                    ExchangeRateFetcher._fetch_service_rates(service)
                    continue

                # Check if service should fetch based on interval type
                if ExchangeRateFetcher._should_fetch_at_hour(service, current_hour):
                    logger.info(
                        f"Fetching rates for {service.name}. "
                        f"Last fetch: {service.last_fetch}, "
                        f"Interval type: {service.interval_type}, "
                        f"Current hour: {current_hour}"
                    )
                    ExchangeRateFetcher._fetch_service_rates(service)
                else:
                    logger.debug(
                        f"Skipping {service.name}. "
                        f"Current hour: {current_hour}, "
                        f"Interval type: {service.interval_type}, "
                        f"Fetch interval: {service.fetch_interval}"
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
                    if service.singleton:
                        # Try to get the last automatically created exchange rate
                        exchange_rate = (
                            ExchangeRate.objects.filter(
                                automatic=True,
                                from_currency=to_currency,
                                to_currency=from_currency,
                            )
                            .order_by("-date")
                            .first()
                        )
                    else:
                        exchange_rate = None

                    if not exchange_rate:
                        ExchangeRate.objects.create(
                            automatic=True,
                            from_currency=to_currency,
                            to_currency=from_currency,
                            rate=rate,
                            date=timezone.now(),
                        )
                    else:
                        exchange_rate.rate = rate
                        exchange_rate.date = timezone.now()
                        exchange_rate.save()

                    processed_pairs.add((to_currency.id, from_currency.id))
                else:
                    # If rates are not inverted, we can use them as is
                    if service.singleton:
                        # Try to get the last automatically created exchange rate
                        exchange_rate = (
                            ExchangeRate.objects.filter(
                                automatic=True,
                                from_currency=from_currency,
                                to_currency=to_currency,
                            )
                            .order_by("-date")
                            .first()
                        )
                    else:
                        exchange_rate = None

                    if not exchange_rate:
                        ExchangeRate.objects.create(
                            automatic=True,
                            from_currency=from_currency,
                            to_currency=to_currency,
                            rate=rate,
                            date=timezone.now(),
                        )
                    else:
                        exchange_rate.rate = rate
                        exchange_rate.date = timezone.now()
                        exchange_rate.save()

                    processed_pairs.add((from_currency.id, to_currency.id))

            service.last_fetch = timezone.now()
            service.save()

        except Exception as e:
            logger.error(f"Error fetching rates for {service.name}: {e}")
