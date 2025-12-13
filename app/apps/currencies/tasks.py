import logging

from procrastinate.contrib.django import app

from apps.currencies.exchange_rates.fetcher import ExchangeRateFetcher

logger = logging.getLogger(__name__)


@app.periodic(cron="0 * * * *")  # Run every hour
@app.task(lock="automatic_fetch_exchange_rates", name="automatic_fetch_exchange_rates")
def automatic_fetch_exchange_rates(timestamp=None):
    """Fetch exchange rates for all due services"""
    fetcher = ExchangeRateFetcher()

    try:
        fetcher.fetch_due_rates()
    except Exception as e:
        logger.error(e, exc_info=True)


@app.task(lock="manual_fetch_exchange_rates", name="manual_fetch_exchange_rates")
def manual_fetch_exchange_rates(timestamp=None):
    """Fetch exchange rates for all due services"""
    fetcher = ExchangeRateFetcher()

    try:
        fetcher.fetch_due_rates(force=True)
    except Exception as e:
        logger.error(e, exc_info=True)
