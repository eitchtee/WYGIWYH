from decimal import Decimal
from unittest import TestCase
from unittest.mock import MagicMock, patch

import requests

from apps.currencies.exchange_rates.fetcher import PROVIDER_MAPPING
from apps.currencies.exchange_rates.providers import AllRatesTodayProvider
from apps.currencies.models import ExchangeRateService


class _FakeCurrency:
    def __init__(self, code, exchange_currency=None):
        self.code = code
        self.exchange_currency = exchange_currency


def _row(base, quote, value, type_="reference"):
    return {"base": base, "quote": quote, "type": type_, "value": value}


def _response(payload):
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = payload
    return response


class AllRatesTodayProviderTests(TestCase):
    def setUp(self):
        self.brl = _FakeCurrency("BRL")
        self.usd = _FakeCurrency("USD")
        self.eur = _FakeCurrency("EUR")
        self.provider = AllRatesTodayProvider("bcb")

    def _get_rates(self, rows, target, base):
        target.exchange_currency = base
        with patch.object(
            self.provider.session, "get", return_value=_response({"rates": rows})
        ):
            return self.provider.get_rates([target], {base})

    def test_requests_the_configured_bank(self):
        self.usd.exchange_currency = self.brl
        payload = {"rates": [_row("USD", "BRL", 5.4)]}

        with patch.object(
            self.provider.session, "get", return_value=_response(payload)
        ) as mock_get:
            self.provider.get_rates([self.usd], {self.brl})

        mock_get.assert_called_once_with(
            "https://allratestoday.com/api/open/central-bank/bcb", timeout=30
        )

    def test_fetches_one_table_for_all_pairs(self):
        self.usd.exchange_currency = self.brl
        self.eur.exchange_currency = self.brl
        payload = {"rates": [_row("USD", "BRL", 5.4), _row("EUR", "BRL", 6.2)]}

        with patch.object(
            self.provider.session, "get", return_value=_response(payload)
        ) as mock_get:
            rates = self.provider.get_rates([self.usd, self.eur], {self.brl})

        mock_get.assert_called_once()
        self.assertEqual(len(rates), 2)

    def test_empty_field_reads_the_ecb_table(self):
        self.assertEqual(AllRatesTodayProvider(None).bank, "ecb")
        self.assertEqual(AllRatesTodayProvider("").bank, "ecb")

    def test_normalizes_the_bank_code(self):
        self.assertEqual(AllRatesTodayProvider("  BCB ").bank, "bcb")

    def test_rejects_malformed_bank_code_without_a_request(self):
        provider = AllRatesTodayProvider("../latest/USD")
        self.usd.exchange_currency = self.brl

        with patch.object(provider.session, "get") as mock_get:
            rates = provider.get_rates([self.usd], {self.brl})

        mock_get.assert_not_called()
        self.assertEqual(rates, [])

    def test_uses_a_row_in_the_requested_direction(self):
        rates = self._get_rates([_row("EUR", "USD", 1.16)], self.usd, self.eur)

        self.assertEqual(rates, [(self.eur, self.usd, Decimal("1.16"))])

    def test_inverts_a_row_in_the_opposite_direction(self):
        # bcb quotes foreign currencies in BRL, so BRL -> USD has to be inverted
        rates = self._get_rates([_row("USD", "BRL", 5)], self.brl, self.usd)
        self.assertEqual(rates, [(self.usd, self.brl, Decimal("5"))])

        rates = self._get_rates([_row("USD", "BRL", 5)], self.usd, self.brl)
        self.assertEqual(rates, [(self.brl, self.usd, Decimal("0.2"))])

    def test_crosses_pairs_through_the_table_home_currency(self):
        rows = [_row("USD", "BRL", 5), _row("EUR", "BRL", 6)]

        rates = self._get_rates(rows, self.eur, self.usd)

        self.assertEqual(len(rates), 1)
        self.assertAlmostEqual(rates[0][2], Decimal("0.8333333"), places=6)

    def test_same_currency_is_one(self):
        rates = self._get_rates([_row("USD", "BRL", 5)], self.usd, self.usd)

        self.assertEqual(rates, [(self.usd, self.usd, Decimal("1"))])

    def test_prefers_the_published_mid_over_buy_and_sell(self):
        rows = [
            _row("USD", "BRL", 5.3, "buy"),
            _row("USD", "BRL", 5.4, "middle"),
            _row("USD", "BRL", 5.7, "sell"),
        ]

        rates = self._get_rates(rows, self.brl, self.usd)

        self.assertEqual(rates, [(self.usd, self.brl, Decimal("5.4"))])

    def test_averages_buy_and_sell_without_a_mid(self):
        rows = [_row("USD", "BRL", 4, "buy"), _row("USD", "BRL", 6, "sell")]

        rates = self._get_rates(rows, self.brl, self.usd)

        self.assertEqual(rates, [(self.usd, self.brl, Decimal("5"))])

    def test_averages_tt_buy_and_sell_without_a_mid(self):
        rows = [
            _row("USD", "MUR", 44.0, "tt_buy"),
            _row("USD", "MUR", 46.0, "tt_sell"),
        ]

        result = self._get_rates(rows, self.usd, _FakeCurrency("MUR"))

        self.assertEqual(result[0][2], Decimal("1") / Decimal("45.0"))

    def test_ignores_rows_of_other_types(self):
        rows = [_row("USD", "BRL", 5, "monthly_average")]

        self.assertEqual(self._get_rates(rows, self.brl, self.usd), [])

    def test_skips_pair_missing_from_the_table(self):
        rows = [_row("USD", "BRL", 5)]

        self.assertEqual(self._get_rates(rows, self.eur, self.usd), [])

    def test_ignores_zero_and_malformed_rows(self):
        rows = ["nope", _row("USD", "BRL", 0), _row("EUR", "BRL", 6)]

        rates = self._get_rates(rows, self.brl, self.eur)

        self.assertEqual(rates, [(self.eur, self.brl, Decimal("6"))])

    def test_logs_a_stale_table_and_still_uses_it(self):
        self.usd.exchange_currency = self.brl
        payload = {
            "stale": True,
            "rate_date": "2026-10-01",
            "rates": [_row("BRL", "USD", 0.2)],
        }

        with patch.object(
            self.provider.session, "get", return_value=_response(payload)
        ):
            with self.assertLogs(
                "apps.currencies.exchange_rates.providers", level="WARNING"
            ) as logs:
                rates = self.provider.get_rates([self.usd], {self.brl})

        self.assertIn("2026-10-01", logs.output[0])
        self.assertEqual(rates, [(self.brl, self.usd, Decimal("0.2"))])

    def test_returns_nothing_on_request_error(self):
        self.usd.exchange_currency = self.brl

        with patch.object(
            self.provider.session,
            "get",
            side_effect=requests.RequestException("404 Not Found"),
        ):
            rates = self.provider.get_rates([self.usd], {self.brl})

        self.assertEqual(rates, [])

    def test_returns_nothing_on_malformed_body(self):
        self.usd.exchange_currency = self.brl

        for payload in ({}, [], {"rates": None}):
            with patch.object(
                self.provider.session, "get", return_value=_response(payload)
            ):
                self.assertEqual(self.provider.get_rates([self.usd], {self.brl}), [])

    def test_returns_nothing_on_non_json_body(self):
        self.usd.exchange_currency = self.brl
        response = _response({})
        response.json.side_effect = ValueError("not json")

        with patch.object(self.provider.session, "get", return_value=response):
            self.assertEqual(self.provider.get_rates([self.usd], {self.brl}), [])

    def test_is_registered_without_an_api_key(self):
        self.assertFalse(AllRatesTodayProvider.requires_api_key())
        self.assertIs(PROVIDER_MAPPING["allratestoday"], AllRatesTodayProvider)
        self.assertEqual(ExchangeRateService.ServiceType.ALLRATESTODAY, "allratestoday")
