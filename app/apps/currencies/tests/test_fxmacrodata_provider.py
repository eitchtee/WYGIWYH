from decimal import Decimal
from unittest import TestCase
from unittest.mock import MagicMock, patch

import requests

from apps.currencies.exchange_rates.fetcher import PROVIDER_MAPPING
from apps.currencies.exchange_rates.providers import FXMacroDataProvider
from apps.currencies.models import ExchangeRateService


class _FakeCurrency:
    def __init__(self, code, exchange_currency=None):
        self.code = code
        self.exchange_currency = exchange_currency


def _response(payload):
    response = MagicMock()
    response.json.return_value = payload
    return response


class FXMacroDataProviderTests(TestCase):
    def setUp(self):
        self.usd = _FakeCurrency("USD")
        self.eur = _FakeCurrency("EUR", exchange_currency=self.usd)
        self.provider = FXMacroDataProvider("test-key")

    def test_sends_api_key_header(self):
        self.assertEqual(self.provider.session.headers["X-API-Key"], "test-key")

    def test_returns_newest_non_null_rate(self):
        payload = {
            "data": [
                {"date": "2026-09-28", "val": None},
                {"date": "2026-09-25", "val": 0.8542},
                {"date": "2026-09-24", "val": 0.8511},
            ]
        }

        with patch.object(
            self.provider.session, "get", return_value=_response(payload)
        ) as mock_get:
            rates = self.provider.get_rates([self.eur], {self.usd})

        mock_get.assert_called_once_with("https://api.fxmacrodata.com/v1/forex/USD/EUR")
        self.assertEqual(rates, [(self.usd, self.eur, Decimal("0.8542"))])

    def test_skips_pair_without_rates(self):
        payload = {"data": [{"date": "2026-09-28", "val": None}]}

        with patch.object(
            self.provider.session, "get", return_value=_response(payload)
        ):
            rates = self.provider.get_rates([self.eur], {self.usd})

        self.assertEqual(rates, [])

    def test_skips_pair_on_request_error(self):
        with patch.object(
            self.provider.session,
            "get",
            side_effect=requests.RequestException("401 Unauthorized"),
        ):
            rates = self.provider.get_rates([self.eur], {self.usd})

        self.assertEqual(rates, [])

    def test_is_registered_with_an_api_key(self):
        self.assertTrue(FXMacroDataProvider.requires_api_key())
        self.assertIs(PROVIDER_MAPPING["fxmacrodata"], FXMacroDataProvider)
        self.assertEqual(ExchangeRateService.ServiceType.FXMACRODATA, "fxmacrodata")
