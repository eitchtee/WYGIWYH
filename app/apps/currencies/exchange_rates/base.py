from abc import ABC, abstractmethod
from decimal import Decimal
from typing import List, Tuple, Optional
from django.db.models import QuerySet

from apps.currencies.models import Currency


class ExchangeRateProvider(ABC):
    rates_inverted = False

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key

    @abstractmethod
    def get_rates(
        self, target_currencies: QuerySet, exchange_currencies: set
    ) -> List[Tuple[Currency, Currency, Decimal]]:
        """Fetch exchange rates for multiple currency pairs"""
        raise NotImplementedError("Subclasses must implement get_rates method")

    @classmethod
    def requires_api_key(cls) -> bool:
        """Return True if the service requires an API key"""
        return True

    @staticmethod
    def invert_rate(rate: Decimal) -> Decimal:
        """Invert the given rate."""
        return Decimal("1") / rate
