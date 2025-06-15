from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from apps.currencies.models import Currency, ExchangeRate, ExchangeRateService
from apps.accounts.models import Account # For ExchangeRateService target_accounts

User = get_user_model()


class BaseCurrencyAppTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="curtestuser@example.com", password="password")
        self.client = Client()
        self.client.login(email="curtestuser@example.com", password="password")

        self.usd = Currency.objects.create(code="USD", name="US Dollar", decimal_places=2, prefix="$")
        self.eur = Currency.objects.create(code="EUR", name="Euro", decimal_places=2, prefix="€")


class CurrencyModelTests(BaseCurrencyAppTest): # Changed from CurrencyTests
    def test_currency_creation(self):
        """Test basic currency creation"""
        # self.usd is already created in BaseCurrencyAppTest
        self.assertEqual(str(self.usd), "US Dollar")
        self.assertEqual(self.usd.code, "USD")
        self.assertEqual(self.usd.decimal_places, 2)
        self.assertEqual(self.usd.prefix, "$")
        # Test creation with suffix
        jpy = Currency.objects.create(code="JPY", name="Japanese Yen", decimal_places=0, suffix="円")
        self.assertEqual(jpy.suffix, "円")


    def test_currency_decimal_places_validation(self):
        """Test decimal places validation for maximum value"""
        currency = Currency(code="TESTMAX", name="Test Currency Max", decimal_places=31)
        with self.assertRaises(ValidationError):
            currency.full_clean()

    def test_currency_decimal_places_negative(self):
        """Test decimal places validation for negative value"""
        currency = Currency(code="TESTNEG", name="Test Currency Neg", decimal_places=-1)
        with self.assertRaises(ValidationError):
            currency.full_clean()

    # Note: unique_code and unique_name tests might behave differently with how Django handles
    # model creation vs full_clean. IntegrityError is caught at DB level.
    # These tests are fine as they are for DB level.

    def test_currency_clean_self_exchange_currency(self):
        """Test that a currency cannot be its own exchange_currency."""
        self.usd.exchange_currency = self.usd
        with self.assertRaises(ValidationError) as context:
            self.usd.full_clean()
        self.assertIn('exchange_currency', context.exception.message_dict)
        self.assertIn("Currency cannot have itself as exchange currency.", context.exception.message_dict['exchange_currency'])


class ExchangeRateModelTests(BaseCurrencyAppTest): # Changed from ExchangeRateTests
    def test_exchange_rate_creation(self):
        """Test basic exchange rate creation"""
        rate = ExchangeRate.objects.create(
            from_currency=self.usd,
            to_currency=self.eur,
            rate=Decimal("0.85"),
            date=timezone.now(),
        )
        self.assertEqual(rate.rate, Decimal("0.85"))
        self.assertIn("USD to EUR", str(rate))

    def test_unique_exchange_rate_constraint(self):
        """Test that duplicate exchange rates for same currency pair and date are prevented"""
        date = timezone.now()
        ExchangeRate.objects.create(
            from_currency=self.usd,
            to_currency=self.eur,
            rate=Decimal("0.85"),
            date=date,
        )
        with self.assertRaises(IntegrityError): # Specifically expect IntegrityError
            ExchangeRate.objects.create(
                from_currency=self.usd,
                to_currency=self.eur,
                rate=Decimal("0.86"), # Different rate, same pair and date
                date=date,
            )

    def test_exchange_rate_clean_same_currency(self):
        """Test that from_currency and to_currency cannot be the same."""
        rate = ExchangeRate(
            from_currency=self.usd,
            to_currency=self.usd, # Same currency
            rate=Decimal("1.00"),
            date=timezone.now()
        )
        with self.assertRaises(ValidationError) as context:
            rate.full_clean()
        self.assertIn('to_currency', context.exception.message_dict)
        self.assertIn("From and To currencies cannot be the same.", context.exception.message_dict['to_currency'])


class ExchangeRateServiceModelTests(BaseCurrencyAppTest):
    def test_service_creation(self):
        service = ExchangeRateService.objects.create(
            name="Test Coingecko Free",
            service_type=ExchangeRateService.ServiceType.COINGECKO_FREE,
            interval_type=ExchangeRateService.IntervalType.EVERY,
            fetch_interval="12" # Every 12 hours
        )
        self.assertEqual(str(service), "Test Coingecko Free")
        self.assertTrue(service.is_active)

    def test_fetch_interval_validation_every_x_hours(self):
        # Valid
        service = ExchangeRateService(
            name="Valid Every", service_type=ExchangeRateService.ServiceType.SYNTH_FINANCE,
            interval_type=ExchangeRateService.IntervalType.EVERY, fetch_interval="6"
        )
        service.full_clean() # Should not raise

        # Invalid - not a digit
        service.fetch_interval = "abc"
        with self.assertRaises(ValidationError) as context:
            service.full_clean()
        self.assertIn("fetch_interval", context.exception.message_dict)
        self.assertIn("'Every X hours' interval type requires a positive integer.", context.exception.message_dict['fetch_interval'][0])

        # Invalid - out of range
        service.fetch_interval = "0"
        with self.assertRaises(ValidationError):
            service.full_clean()
        service.fetch_interval = "25"
        with self.assertRaises(ValidationError):
            service.full_clean()

    def test_fetch_interval_validation_on_not_on(self):
        # Valid examples for 'on' or 'not_on'
        valid_intervals = ["1", "0,12", "1-5", "1-5,8,10-12", "0,1,2,3,22,23"]
        for interval in valid_intervals:
            service = ExchangeRateService(
                name=f"Test On {interval}", service_type=ExchangeRateService.ServiceType.SYNTH_FINANCE,
                interval_type=ExchangeRateService.IntervalType.ON, fetch_interval=interval
            )
            service.full_clean() # Should not raise
            # Check normalized form (optional, but good if model does it)
            # self.assertEqual(service.fetch_interval, ",".join(str(h) for h in sorted(service._parse_hour_ranges(interval))))


        invalid_intervals = [
            "abc", "1-", "-5", "24", "-1", "1-24", "1,2,25", "5-1", # Invalid hour, range, or format
            "1.5", "1, 2, 3," # decimal, trailing comma
        ]
        for interval in invalid_intervals:
            service = ExchangeRateService(
                name=f"Test On Invalid {interval}", service_type=ExchangeRateService.ServiceType.SYNTH_FINANCE,
                interval_type=ExchangeRateService.IntervalType.NOT_ON, fetch_interval=interval
            )
            with self.assertRaises(ValidationError) as context:
                service.full_clean()
            self.assertIn("fetch_interval", context.exception.message_dict)
            self.assertTrue("Invalid hour format" in context.exception.message_dict['fetch_interval'][0] or \
                            "Hours must be between 0 and 23" in context.exception.message_dict['fetch_interval'][0] or \
                            "Invalid range" in context.exception.message_dict['fetch_interval'][0]
            )


    @patch('apps.currencies.exchange_rates.fetcher.PROVIDER_MAPPING')
    def test_get_provider(self, mock_provider_mapping):
        # Mock a provider class
        class MockProvider:
            def __init__(self, api_key=None):
                self.api_key = api_key
        mock_provider_mapping.__getitem__.return_value = MockProvider

        service = ExchangeRateService(
            name="Test Get Provider",
            service_type=ExchangeRateService.ServiceType.COINGECKO_FREE, # Any valid choice
            api_key="testkey"
        )
        provider_instance = service.get_provider()
        self.assertIsInstance(provider_instance, MockProvider)
        self.assertEqual(provider_instance.api_key, "testkey")
        mock_provider_mapping.__getitem__.assert_called_with(ExchangeRateService.ServiceType.COINGECKO_FREE)


class CurrencyViewTests(BaseCurrencyAppTest):
    def test_currency_list_view(self):
        response = self.client.get(reverse("currencies_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.usd.name)
        self.assertContains(response, self.eur.name)

    def test_currency_add_view(self):
        data = {"code": "GBP", "name": "British Pound", "decimal_places": 2, "prefix": "£"}
        response = self.client.post(reverse("currency_add"), data)
        self.assertEqual(response.status_code, 204) # HTMX success
        self.assertTrue(Currency.objects.filter(code="GBP").exists())

    def test_currency_edit_view(self):
        gbp = Currency.objects.create(code="GBP", name="Pound Sterling", decimal_places=2)
        data = {"code": "GBP", "name": "British Pound Sterling", "decimal_places": 2, "prefix": "£"}
        response = self.client.post(reverse("currency_edit", args=[gbp.id]), data)
        self.assertEqual(response.status_code, 204)
        gbp.refresh_from_db()
        self.assertEqual(gbp.name, "British Pound Sterling")

    def test_currency_delete_view(self):
        cad = Currency.objects.create(code="CAD", name="Canadian Dollar", decimal_places=2)
        response = self.client.delete(reverse("currency_delete", args=[cad.id]))
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Currency.objects.filter(code="CAD").exists())


class ExchangeRateViewTests(BaseCurrencyAppTest):
    def test_exchange_rate_list_view_main(self):
        # This view lists pairs, not individual rates directly in the main list
        ExchangeRate.objects.create(from_currency=self.usd, to_currency=self.eur, rate=Decimal("0.9"), date=timezone.now())
        response = self.client.get(reverse("exchange_rates_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.usd.name) # Check if pair components are mentioned
        self.assertContains(response, self.eur.name)

    def test_exchange_rate_list_pair_view(self):
        rate_date = timezone.now()
        ExchangeRate.objects.create(from_currency=self.usd, to_currency=self.eur, rate=Decimal("0.9"), date=rate_date)
        url = reverse("exchange_rates_list_pair") + f"?from={self.usd.name}&to={self.eur.name}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "0.9") # Check if the rate is displayed

    def test_exchange_rate_add_view(self):
        data = {
            "from_currency": self.usd.id,
            "to_currency": self.eur.id,
            "rate": "0.88",
            "date": timezone.now().strftime('%Y-%m-%d %H:%M:%S') # Match form field format
        }
        response = self.client.post(reverse("exchange_rate_add"), data)
        self.assertEqual(response.status_code, 204, response.content.decode() if response.content and response.status_code != 204 else "No content on 204")
        self.assertTrue(ExchangeRate.objects.filter(from_currency=self.usd, to_currency=self.eur, rate=Decimal("0.88")).exists())

    def test_exchange_rate_edit_view(self):
        rate = ExchangeRate.objects.create(from_currency=self.usd, to_currency=self.eur, rate=Decimal("0.91"), date=timezone.now())
        data = {
            "from_currency": self.usd.id,
            "to_currency": self.eur.id,
            "rate": "0.92",
            "date": rate.date.strftime('%Y-%m-%d %H:%M:%S')
        }
        response = self.client.post(reverse("exchange_rate_edit", args=[rate.id]), data)
        self.assertEqual(response.status_code, 204)
        rate.refresh_from_db()
        self.assertEqual(rate.rate, Decimal("0.92"))

    def test_exchange_rate_delete_view(self):
        rate = ExchangeRate.objects.create(from_currency=self.usd, to_currency=self.eur, rate=Decimal("0.93"), date=timezone.now())
        response = self.client.delete(reverse("exchange_rate_delete", args=[rate.id]))
        self.assertEqual(response.status_code, 204)
        self.assertFalse(ExchangeRate.objects.filter(id=rate.id).exists())


class ExchangeRateServiceViewTests(BaseCurrencyAppTest):
    def test_exchange_rate_service_list_view(self):
        service = ExchangeRateService.objects.create(name="My Test Service", service_type=ExchangeRateService.ServiceType.SYNTH_FINANCE, fetch_interval="1")
        response = self.client.get(reverse("exchange_rates_services_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, service.name)

    def test_exchange_rate_service_add_view(self):
        data = {
            "name": "New Fetcher Service",
            "service_type": ExchangeRateService.ServiceType.COINGECKO_FREE,
            "is_active": "on",
            "interval_type": ExchangeRateService.IntervalType.EVERY,
            "fetch_interval": "24",
            # target_currencies and target_accounts are M2M, handled differently or optional
        }
        response = self.client.post(reverse("exchange_rate_service_add"), data)
        self.assertEqual(response.status_code, 204)
        self.assertTrue(ExchangeRateService.objects.filter(name="New Fetcher Service").exists())

    def test_exchange_rate_service_edit_view(self):
        service = ExchangeRateService.objects.create(name="Editable Service", service_type=ExchangeRateService.ServiceType.SYNTH_FINANCE, fetch_interval="1")
        data = {
            "name": "Edited Fetcher Service",
            "service_type": service.service_type,
            "is_active": "on",
            "interval_type": service.interval_type,
            "fetch_interval": "6", # Changed interval
        }
        response = self.client.post(reverse("exchange_rate_service_edit", args=[service.id]), data)
        self.assertEqual(response.status_code, 204)
        service.refresh_from_db()
        self.assertEqual(service.name, "Edited Fetcher Service")
        self.assertEqual(service.fetch_interval, "6")

    def test_exchange_rate_service_delete_view(self):
        service = ExchangeRateService.objects.create(name="Deletable Service", service_type=ExchangeRateService.ServiceType.SYNTH_FINANCE, fetch_interval="1")
        response = self.client.delete(reverse("exchange_rate_service_delete", args=[service.id]))
        self.assertEqual(response.status_code, 204)
        self.assertFalse(ExchangeRateService.objects.filter(id=service.id).exists())

    @patch('apps.currencies.tasks.manual_fetch_exchange_rates.defer')
    def test_exchange_rate_service_force_fetch_view(self, mock_defer):
        response = self.client.get(reverse("exchange_rate_service_force_fetch"))
        self.assertEqual(response.status_code, 204) # Triggers toast
        mock_defer.assert_called_once()
