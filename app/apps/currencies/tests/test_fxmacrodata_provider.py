import threading
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, HTTPServer
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
    response.status_code = 200
    response.json.return_value = payload
    return response


class _RedirectHandler(BaseHTTPRequestHandler):
    requested = []

    def do_GET(self):
        self.requested.append(self.path)
        self.send_response(302)
        self.send_header("Location", "/elsewhere")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):
        pass


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

        mock_get.assert_called_once_with(
            "https://api.fxmacrodata.com/v1/forex/USD/EUR", allow_redirects=False
        )
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

    def test_does_not_follow_redirects(self):
        _RedirectHandler.requested = []
        server = HTTPServer(("127.0.0.1", 0), _RedirectHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base_url = f"http://127.0.0.1:{server.server_port}/v1/forex"

        with patch.object(FXMacroDataProvider, "BASE_URL", base_url):
            with self.assertLogs(
                "apps.currencies.exchange_rates.providers", "ERROR"
            ) as logs:
                rates = self.provider.get_rates([self.eur], {self.usd})

        self.assertEqual(rates, [])
        self.assertEqual(_RedirectHandler.requested, ["/v1/forex/USD/EUR"])
        self.assertIn("redirected", logs.output[0])
        self.assertNotIn("test-key", "".join(logs.output))

    def test_strips_whitespace_around_api_key(self):
        provider = FXMacroDataProvider("  test-key\n")

        self.assertEqual(provider.session.headers["X-API-Key"], "test-key")

    def test_rejects_malformed_api_key_without_logging_it(self):
        for api_key in ("test-key\r\nX-Injected: 1", "test key", "test-key\x00"):
            provider = FXMacroDataProvider(api_key)

            with patch.object(provider.session, "get") as mock_get:
                with self.assertLogs(
                    "apps.currencies.exchange_rates.providers", "ERROR"
                ) as logs:
                    rates = provider.get_rates([self.eur], {self.usd})

            self.assertEqual(rates, [])
            mock_get.assert_not_called()
            self.assertNotIn("test", "".join(logs.output))

    def test_logs_api_detail_when_data_is_missing(self):
        with patch.object(
            self.provider.session,
            "get",
            return_value=_response({"detail": "Invalid API key"}),
        ):
            with self.assertLogs(
                "apps.currencies.exchange_rates.providers", "ERROR"
            ) as logs:
                rates = self.provider.get_rates([self.eur], {self.usd})

        self.assertEqual(rates, [])
        self.assertIn("Invalid API key", logs.output[0])

    def test_skips_pair_on_malformed_body(self):
        not_json = _response(None)
        not_json.json.side_effect = ValueError("Expecting value")

        for response in (not_json, _response([]), _response({"data": {}})):
            with patch.object(self.provider.session, "get", return_value=response):
                with self.assertLogs(
                    "apps.currencies.exchange_rates.providers", "ERROR"
                ):
                    rates = self.provider.get_rates([self.eur], {self.usd})

            self.assertEqual(rates, [])

    def test_ignores_rows_that_are_not_objects(self):
        payload = {"data": ["oops", {"date": "2026-09-25", "val": 0.8542}]}

        with patch.object(
            self.provider.session, "get", return_value=_response(payload)
        ):
            rates = self.provider.get_rates([self.eur], {self.usd})

        self.assertEqual(rates, [(self.usd, self.eur, Decimal("0.8542"))])

    def test_is_registered_with_an_api_key(self):
        self.assertTrue(FXMacroDataProvider.requires_api_key())
        self.assertIs(PROVIDER_MAPPING["fxmacrodata"], FXMacroDataProvider)
        self.assertEqual(ExchangeRateService.ServiceType.FXMACRODATA, "fxmacrodata")
