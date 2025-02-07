import logging
import time

import requests
from decimal import Decimal
from typing import Tuple, List

from django.db.models import QuerySet

from apps.currencies.models import Currency
from apps.currencies.exchange_rates.base import ExchangeRateProvider

logger = logging.getLogger(__name__)


class SynthFinanceProvider(ExchangeRateProvider):
    """Implementation for Synth Finance API (synthfinance.com)"""

    BASE_URL = "https://api.synthfinance.com/rates/live"
    rates_inverted = False  # SynthFinance returns non-inverted rates

    def __init__(self, api_key: str = None):
        super().__init__(api_key)
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {self.api_key}"})

    def get_rates(
        self, target_currencies: QuerySet, exchange_currencies: set
    ) -> List[Tuple[Currency, Currency, Decimal]]:
        results = []
        currency_groups = {}
        for currency in target_currencies:
            if currency.exchange_currency in exchange_currencies:
                group = currency_groups.setdefault(currency.exchange_currency.code, [])
                group.append(currency)

        for base_currency, currencies in currency_groups.items():
            try:
                to_currencies = ",".join(
                    currency.code
                    for currency in currencies
                    if currency.code != base_currency
                )
                response = self.session.get(
                    f"{self.BASE_URL}",
                    params={"from": base_currency, "to": to_currencies},
                )
                response.raise_for_status()
                data = response.json()
                rates = data["data"]["rates"]

                for currency in currencies:
                    if currency.code == base_currency:
                        rate = Decimal("1")
                    else:
                        rate = Decimal(str(rates[currency.code]))
                    # Return the rate as is, without inversion
                    results.append((currency.exchange_currency, currency, rate))

                credits_used = data["meta"]["credits_used"]
                credits_remaining = data["meta"]["credits_remaining"]
                logger.info(
                    f"Synth Finance API call: {credits_used} credits used, {credits_remaining} remaining"
                )
            except requests.RequestException as e:
                logger.error(
                    f"Error fetching rates from Synth Finance API for base {base_currency}: {e}"
                )
            except KeyError as e:
                logger.error(
                    f"Unexpected response structure from Synth Finance API for base {base_currency}: {e}"
                )
            except Exception as e:
                logger.error(
                    f"Unexpected error processing Synth Finance data for base {base_currency}: {e}"
                )
        return results


class CoinGeckoFreeProvider(ExchangeRateProvider):
    """Implementation for CoinGecko Free API"""

    BASE_URL = "https://api.coingecko.com/api/v3"
    rates_inverted = True

    def __init__(self, api_key: str):
        super().__init__(api_key)
        self.session = requests.Session()
        self.session.headers.update({"x-cg-demo-api-key": api_key})

    @classmethod
    def requires_api_key(cls) -> bool:
        return True

    def get_rates(
        self, target_currencies: QuerySet, exchange_currencies: set
    ) -> List[Tuple[Currency, Currency, Decimal]]:
        results = []
        all_currencies = set(currency.code.lower() for currency in target_currencies)
        all_currencies.update(currency.code.lower() for currency in exchange_currencies)

        try:
            response = self.session.get(
                f"{self.BASE_URL}/simple/price",
                params={
                    "ids": ",".join(all_currencies),
                    "vs_currencies": ",".join(all_currencies),
                },
            )
            response.raise_for_status()
            rates_data = response.json()

            for target_currency in target_currencies:
                if target_currency.exchange_currency in exchange_currencies:
                    try:
                        rate = Decimal(
                            str(
                                rates_data[target_currency.code.lower()][
                                    target_currency.exchange_currency.code.lower()
                                ]
                            )
                        )
                        # The rate is already inverted, so we don't need to invert it again
                        results.append(
                            (target_currency.exchange_currency, target_currency, rate)
                        )
                    except KeyError:
                        logger.error(
                            f"Rate not found for {target_currency.code} or {target_currency.exchange_currency.code}"
                        )
                    except Exception as e:
                        logger.error(
                            f"Error calculating rate for {target_currency.code}: {e}"
                        )

            time.sleep(1)  # CoinGecko allows 10-30 calls/minute for free tier
        except requests.RequestException as e:
            logger.error(f"Error fetching rates from CoinGecko API: {e}")

        return results


class CoinGeckoProProvider(CoinGeckoFreeProvider):
    """Implementation for CoinGecko Pro API"""

    BASE_URL = "https://pro-api.coingecko.com/api/v3/simple/price"
    rates_inverted = True

    def __init__(self, api_key: str):
        super().__init__(api_key)
        self.session = requests.Session()
        self.session.headers.update({"x-cg-pro-api-key": api_key})
