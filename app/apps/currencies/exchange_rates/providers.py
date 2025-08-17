import logging
import time

import requests
from decimal import Decimal
from typing import Tuple, List, Optional, Dict

from django.db.models import QuerySet

from apps.currencies.models import Currency, ExchangeRate
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


class SynthFinanceStockProvider(ExchangeRateProvider):
    """Implementation for Synth Finance API Real-Time Prices endpoint (synthfinance.com)"""

    BASE_URL = "https://api.synthfinance.com/tickers"
    rates_inverted = True

    def __init__(self, api_key: str = None):
        super().__init__(api_key)
        self.session = requests.Session()
        self.session.headers.update(
            {"Authorization": f"Bearer {self.api_key}", "accept": "application/json"}
        )

    def get_rates(
        self, target_currencies: QuerySet, exchange_currencies: set
    ) -> List[Tuple[Currency, Currency, Decimal]]:
        results = []

        for currency in target_currencies:
            if currency.exchange_currency not in exchange_currencies:
                continue

            try:
                # Same currency has rate of 1
                if currency.code == currency.exchange_currency.code:
                    rate = Decimal("1")
                    results.append((currency.exchange_currency, currency, rate))
                    continue

                # Fetch real-time price for this ticker
                response = self.session.get(
                    f"{self.BASE_URL}/{currency.code}/real-time"
                )
                response.raise_for_status()
                data = response.json()

                # Use fair market value as the rate
                rate = Decimal(data["data"]["fair_market_value"])
                results.append((currency.exchange_currency, currency, rate))

                # Log API usage
                credits_used = data["meta"]["credits_used"]
                credits_remaining = data["meta"]["credits_remaining"]
                logger.info(
                    f"Synth Finance API call for {currency.code}: {credits_used} credits used, {credits_remaining} remaining"
                )
            except requests.RequestException as e:
                logger.error(
                    f"Error fetching rate from Synth Finance API for ticker {currency.code}: {e}",
                    exc_info=True,
                )
            except KeyError as e:
                logger.error(
                    f"Unexpected response structure from Synth Finance API for ticker {currency.code}: {e}",
                    exc_info=True,
                )
            except Exception as e:
                logger.error(
                    f"Unexpected error processing Synth Finance data for ticker {currency.code}: {e}",
                    exc_info=True,
                )

        return results


class TransitiveRateProvider(ExchangeRateProvider):
    """Calculates exchange rates through paths of existing rates"""

    rates_inverted = True

    def __init__(self, api_key: str = None):
        super().__init__(api_key)  # API key not needed but maintaining interface

    @classmethod
    def requires_api_key(cls) -> bool:
        return False

    def get_rates(
        self, target_currencies: QuerySet, exchange_currencies: set
    ) -> List[Tuple[Currency, Currency, Decimal]]:
        results = []

        # Get recent rates for building the graph
        recent_rates = ExchangeRate.objects.all()

        # Build currency graph
        currency_graph = self._build_currency_graph(recent_rates)

        for target in target_currencies:
            if (
                not target.exchange_currency
                or target.exchange_currency not in exchange_currencies
            ):
                continue

            # Find path and calculate rate
            from_id = target.exchange_currency.id
            to_id = target.id

            path, rate = self._find_conversion_path(currency_graph, from_id, to_id)

            if path and rate:
                path_codes = [Currency.objects.get(id=cid).code for cid in path]
                logger.info(
                    f"Found conversion path: {' -> '.join(path_codes)}, rate: {rate}"
                )
                results.append((target.exchange_currency, target, rate))
            else:
                logger.debug(
                    f"No conversion path found for {target.exchange_currency.code}->{target.code}"
                )

        return results

    @staticmethod
    def _build_currency_graph(rates) -> Dict[int, Dict[int, Decimal]]:
        """Build a graph representation of currency relationships"""
        graph = {}

        for rate in rates:
            # Add both directions to make the graph bidirectional
            if rate.from_currency_id not in graph:
                graph[rate.from_currency_id] = {}
            graph[rate.from_currency_id][rate.to_currency_id] = rate.rate

            if rate.to_currency_id not in graph:
                graph[rate.to_currency_id] = {}
            graph[rate.to_currency_id][rate.from_currency_id] = Decimal("1") / rate.rate

        return graph

    @staticmethod
    def _find_conversion_path(
        graph, from_id, to_id
    ) -> Tuple[Optional[list], Optional[Decimal]]:
        """Find the shortest path between currencies using breadth-first search"""
        if from_id not in graph or to_id not in graph:
            return None, None

        queue = [(from_id, [from_id], Decimal("1"))]
        visited = {from_id}

        while queue:
            current, path, current_rate = queue.pop(0)

            if current == to_id:
                return path, current_rate

            for neighbor, rate in graph.get(current, {}).items():
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor], current_rate * rate))

        return None, None


class FrankfurterProvider(ExchangeRateProvider):
    """Implementation for the Frankfurter API (frankfurter.dev)"""

    BASE_URL = "https://api.frankfurter.dev/v1/latest"
    rates_inverted = (
        False  # Frankfurter returns non-inverted rates (e.g., 1 EUR = 1.1 USD)
    )

    def __init__(self, api_key: str = None):
        """
        Initializes the provider. The Frankfurter API does not require an API key,
        so the api_key parameter is ignored.
        """
        super().__init__(api_key)
        self.session = requests.Session()

    @classmethod
    def requires_api_key(cls) -> bool:
        return False

    def get_rates(
        self, target_currencies: QuerySet, exchange_currencies: set
    ) -> List[Tuple[Currency, Currency, Decimal]]:
        results = []
        currency_groups = {}
        # Group target currencies by their exchange (base) currency to minimize API calls
        for currency in target_currencies:
            if currency.exchange_currency in exchange_currencies:
                group = currency_groups.setdefault(currency.exchange_currency.code, [])
                group.append(currency)

        # Make one API call for each base currency
        for base_currency, currencies in currency_groups.items():
            try:
                # Create a comma-separated list of target currency codes
                to_currencies = ",".join(
                    currency.code
                    for currency in currencies
                    if currency.code != base_currency
                )

                # If there are no target currencies other than the base, skip the API call
                if not to_currencies:
                    # Handle the case where the only request is for the base rate (e.g., USD to USD)
                    for currency in currencies:
                        if currency.code == base_currency:
                            results.append(
                                (currency.exchange_currency, currency, Decimal("1"))
                            )
                    continue

                response = self.session.get(
                    self.BASE_URL,
                    params={"base": base_currency, "symbols": to_currencies},
                )
                response.raise_for_status()
                data = response.json()
                rates = data["rates"]

                # Process the returned rates
                for currency in currencies:
                    if currency.code == base_currency:
                        # The rate for the base currency to itself is always 1
                        rate = Decimal("1")
                    else:
                        rate = Decimal(str(rates[currency.code]))

                    results.append((currency.exchange_currency, currency, rate))

            except requests.RequestException as e:
                logger.error(
                    f"Error fetching rates from Frankfurter API for base {base_currency}: {e}"
                )
            except KeyError as e:
                logger.error(
                    f"Unexpected response structure from Frankfurter API for base {base_currency}: {e}"
                )
            except Exception as e:
                logger.error(
                    f"Unexpected error processing Frankfurter data for base {base_currency}: {e}"
                )
        return results
