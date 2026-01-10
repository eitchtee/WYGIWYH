from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.utils import timezone

from apps.currencies.models import Currency, ExchangeRateService
from apps.currencies.exchange_rates.fetcher import ExchangeRateFetcher


class ExchangeRateServiceFailureTrackingTests(TestCase):
    """Tests for the failure count tracking functionality."""

    def setUp(self):
        """Set up test data."""
        self.usd = Currency.objects.create(
            code="USD", name="US Dollar", decimal_places=2, prefix="$ "
        )
        self.eur = Currency.objects.create(
            code="EUR", name="Euro", decimal_places=2, prefix="€ "
        )
        self.eur.exchange_currency = self.usd
        self.eur.save()

        self.service = ExchangeRateService.objects.create(
            name="Test Service",
            service_type=ExchangeRateService.ServiceType.FRANKFURTER,
            is_active=True,
        )
        self.service.target_currencies.add(self.eur)

    def test_failure_count_increments_on_provider_error(self):
        """Test that failure_count increments when provider raises an exception."""
        self.assertEqual(self.service.failure_count, 0)

        with patch.object(
            self.service, "get_provider", side_effect=Exception("API Error")
        ):
            ExchangeRateFetcher._fetch_service_rates(self.service)

        self.service.refresh_from_db()
        self.assertEqual(self.service.failure_count, 1)

    def test_failure_count_resets_on_success(self):
        """Test that failure_count resets to 0 on successful fetch."""
        # Set initial failure count
        self.service.failure_count = 5
        self.service.save()

        # Mock a successful provider
        mock_provider = MagicMock()
        mock_provider.requires_api_key.return_value = False
        mock_provider.get_rates.return_value = [(self.usd, self.eur, Decimal("0.85"))]
        mock_provider.rates_inverted = False

        with patch.object(self.service, "get_provider", return_value=mock_provider):
            ExchangeRateFetcher._fetch_service_rates(self.service)

        self.service.refresh_from_db()
        self.assertEqual(self.service.failure_count, 0)

    def test_failure_count_accumulates_across_fetches(self):
        """Test that failure_count accumulates with consecutive failures."""
        self.assertEqual(self.service.failure_count, 0)

        with patch.object(
            self.service, "get_provider", side_effect=Exception("API Error")
        ):
            ExchangeRateFetcher._fetch_service_rates(self.service)
            self.service.refresh_from_db()
            self.assertEqual(self.service.failure_count, 1)

            ExchangeRateFetcher._fetch_service_rates(self.service)
            self.service.refresh_from_db()
            self.assertEqual(self.service.failure_count, 2)

            ExchangeRateFetcher._fetch_service_rates(self.service)
            self.service.refresh_from_db()
            self.assertEqual(self.service.failure_count, 3)

    def test_last_fetch_not_updated_on_failure(self):
        """Test that last_fetch is NOT updated when a failure occurs."""
        original_last_fetch = self.service.last_fetch
        self.assertIsNone(original_last_fetch)

        with patch.object(
            self.service, "get_provider", side_effect=Exception("API Error")
        ):
            ExchangeRateFetcher._fetch_service_rates(self.service)

        self.service.refresh_from_db()
        self.assertIsNone(self.service.last_fetch)
        self.assertEqual(self.service.failure_count, 1)

    def test_last_fetch_updated_on_success(self):
        """Test that last_fetch IS updated when fetch succeeds."""
        self.assertIsNone(self.service.last_fetch)

        mock_provider = MagicMock()
        mock_provider.requires_api_key.return_value = False
        mock_provider.get_rates.return_value = [(self.usd, self.eur, Decimal("0.85"))]
        mock_provider.rates_inverted = False

        with patch.object(self.service, "get_provider", return_value=mock_provider):
            ExchangeRateFetcher._fetch_service_rates(self.service)

        self.service.refresh_from_db()
        self.assertIsNotNone(self.service.last_fetch)
        self.assertEqual(self.service.failure_count, 0)
