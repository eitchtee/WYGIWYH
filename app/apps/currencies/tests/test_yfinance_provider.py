from decimal import Decimal
from unittest import TestCase

from apps.currencies.exchange_rates.fetcher import PROVIDER_MAPPING
from apps.currencies.exchange_rates.providers import YFinanceMarketsProvider
from apps.currencies.models import ExchangeRateService


class _FakeSeries:
    def __init__(self, values):
        self._values = values

    def dropna(self):
        return _FakeSeries([value for value in self._values if value is not None])

    @property
    def iloc(self):
        return self

    def __getitem__(self, index):
        return self._values[index]


class _FakeHistory:
    def __init__(self, close_values):
        self._close_values = close_values
        self.empty = not close_values

    def __getitem__(self, field):
        if field != "Close":
            raise KeyError(field)
        return _FakeSeries(self._close_values)


class _FakeCurrency:
    def __init__(self, code, exchange_currency=None):
        self.code = code
        self.exchange_currency = exchange_currency


class _FakeTicker:
    def __init__(self, history):
        self.history_result = history
        self.history_kwargs = None

    def history(self, **kwargs):
        self.history_kwargs = kwargs
        return self.history_result


class YFinanceMarketsProviderTests(TestCase):
    def setUp(self):
        self.brl = _FakeCurrency("BRL")
        self.asset = _FakeCurrency("AAPL", exchange_currency=self.brl)

    def test_returns_latest_hourly_close_using_symbol_verbatim(self):
        ticker = _FakeTicker(_FakeHistory([36.90, None, 37.42]))
        requested_symbols = []

        def ticker_factory(symbol):
            requested_symbols.append(symbol)
            return ticker

        provider = YFinanceMarketsProvider(ticker_factory=ticker_factory)

        rates = provider.get_rates([self.asset], {self.brl})

        self.assertEqual(rates, [(self.brl, self.asset, Decimal("37.42"))])
        self.assertEqual(requested_symbols, ["AAPL"])
        self.assertEqual(
            ticker.history_kwargs,
            {"period": "5d", "interval": "1h", "auto_adjust": False},
        )

    def test_passes_brazilian_symbol_verbatim_and_skips_empty_history(self):
        self.asset.code = "PETR4.SA"
        ticker = _FakeTicker(_FakeHistory([]))
        requested_symbols = []

        provider = YFinanceMarketsProvider(
            ticker_factory=lambda symbol: requested_symbols.append(symbol)
            or ticker
        )

        rates = provider.get_rates([self.asset], {self.brl})

        self.assertEqual(rates, [])
        self.assertEqual(requested_symbols, ["PETR4.SA"])

    def test_is_registered_without_an_api_key(self):
        self.assertFalse(YFinanceMarketsProvider.requires_api_key())
        self.assertIs(PROVIDER_MAPPING["yfinance"], YFinanceMarketsProvider)
        self.assertEqual(ExchangeRateService.ServiceType.YFINANCE, "yfinance")
