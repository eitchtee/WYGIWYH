from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth.models import User # Added for ERS owner
from datetime import date # Added for CurrencyConversionUtilsTests
from apps.currencies.utils.convert import get_exchange_rate, convert # Added convert
from unittest.mock import patch # Added patch

from apps.currencies.models import Currency, ExchangeRate, ExchangeRateService


class CurrencyTests(TestCase):
    def test_currency_creation(self):
        """Test basic currency creation"""
        currency = Currency.objects.create(
            code="USD", name="US Dollar", decimal_places=2, prefix="$ ", suffix=" END "
        )
        self.assertEqual(str(currency), "US Dollar")
        self.assertEqual(currency.code, "USD")
        self.assertEqual(currency.decimal_places, 2)
        self.assertEqual(currency.prefix, "$ ")
        self.assertEqual(currency.suffix, " END ")

    def test_currency_decimal_places_validation(self):
        """Test decimal places validation for maximum value"""
        currency = Currency(
            code="TEST",
            name="Test Currency",
            decimal_places=31,  # Should fail as max is 30
        )
        with self.assertRaises(ValidationError):
            currency.full_clean()

    def test_currency_decimal_places_negative(self):
        """Test decimal places validation for negative value"""
        currency = Currency(
            code="TEST",
            name="Test Currency",
            decimal_places=-1,  # Should fail as min is 0
        )
        with self.assertRaises(ValidationError):
            currency.full_clean()

    def test_currency_unique_code(self):
        """Test that currency codes must be unique"""
        Currency.objects.create(code="USD", name="US Dollar", decimal_places=2)
        with self.assertRaises(IntegrityError):
            Currency.objects.create(code="USD", name="Another Dollar", decimal_places=2)

    def test_currency_unique_name(self):
        """Test that currency names must be unique"""
        Currency.objects.create(code="USD", name="US Dollar", decimal_places=2)
        with self.assertRaises(IntegrityError):
            Currency.objects.create(code="USD2", name="US Dollar", decimal_places=2)

    def test_currency_exchange_currency_cannot_be_self(self):
        """Test that a currency's exchange_currency cannot be itself."""
        currency = Currency.objects.create(
            code="XYZ", name="Test XYZ", decimal_places=2
        )
        currency.exchange_currency = currency  # Set exchange_currency to self

        with self.assertRaises(ValidationError) as cm:
            currency.full_clean()

        self.assertIn('exchange_currency', cm.exception.error_dict)
        # Optionally, check for a specific error message if known:
        # self.assertTrue(any("cannot be the same as the currency itself" in e.message
        #                     for e in cm.exception.error_dict['exchange_currency']))


class ExchangeRateServiceTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='ers_owner', password='password123')
        self.base_currency = Currency.objects.create(code="BSC", name="Base Service Coin", decimal_places=2)
        self.default_ers_params = {
            'name': "Test ERS",
            'owner': self.owner,
            'base_currency': self.base_currency,
            'provider_class': "dummy.provider.ClassName", # Placeholder
        }

    def _create_ers_instance(self, interval_type, fetch_interval, **kwargs):
        params = {**self.default_ers_params, 'interval_type': interval_type, 'fetch_interval': fetch_interval, **kwargs}
        return ExchangeRateService(**params)

    # Tests for IntervalType.EVERY
    def test_ers_interval_every_valid_integer(self):
        ers = self._create_ers_instance(ExchangeRateService.IntervalType.EVERY, "12")
        try:
            ers.full_clean()
        except ValidationError:
            self.fail("ValidationError raised unexpectedly for valid 'EVERY' interval '12'.")

    def test_ers_interval_every_invalid_not_integer(self):
        ers = self._create_ers_instance(ExchangeRateService.IntervalType.EVERY, "abc")
        with self.assertRaises(ValidationError) as cm:
            ers.full_clean()
        self.assertIn('fetch_interval', cm.exception.error_dict)

    def test_ers_interval_every_invalid_too_low(self):
        ers = self._create_ers_instance(ExchangeRateService.IntervalType.EVERY, "0")
        with self.assertRaises(ValidationError) as cm:
            ers.full_clean()
        self.assertIn('fetch_interval', cm.exception.error_dict)

    def test_ers_interval_every_invalid_too_high(self):
        ers = self._create_ers_instance(ExchangeRateService.IntervalType.EVERY, "25") # Max is 24 for 'EVERY'
        with self.assertRaises(ValidationError) as cm:
            ers.full_clean()
        self.assertIn('fetch_interval', cm.exception.error_dict)

    # Tests for IntervalType.ON (and by extension NOT_ON, as validation logic is shared)
    def test_ers_interval_on_not_on_valid_single_hour(self):
        ers = self._create_ers_instance(ExchangeRateService.IntervalType.ON, "5")
        try:
            ers.full_clean() # Should normalize to "5" if not already
        except ValidationError:
            self.fail("ValidationError raised unexpectedly for valid 'ON' interval '5'.")
        self.assertEqual(ers.fetch_interval, "5")


    def test_ers_interval_on_not_on_valid_multiple_hours(self):
        ers = self._create_ers_instance(ExchangeRateService.IntervalType.ON, "1,8,22")
        try:
            ers.full_clean()
        except ValidationError:
            self.fail("ValidationError raised unexpectedly for valid 'ON' interval '1,8,22'.")
        self.assertEqual(ers.fetch_interval, "1,8,22")


    def test_ers_interval_on_not_on_valid_range(self):
        ers = self._create_ers_instance(ExchangeRateService.IntervalType.ON, "0-4")
        ers.full_clean() # Should not raise ValidationError
        self.assertEqual(ers.fetch_interval, "0,1,2,3,4")

    def test_ers_interval_on_not_on_valid_mixed(self):
        ers = self._create_ers_instance(ExchangeRateService.IntervalType.ON, "1-3,8,10-12")
        ers.full_clean() # Should not raise ValidationError
        self.assertEqual(ers.fetch_interval, "1,2,3,8,10,11,12")

    def test_ers_interval_on_not_on_invalid_char(self):
        ers = self._create_ers_instance(ExchangeRateService.IntervalType.ON, "1-3,a")
        with self.assertRaises(ValidationError) as cm:
            ers.full_clean()
        self.assertIn('fetch_interval', cm.exception.error_dict)

    def test_ers_interval_on_not_on_invalid_hour_too_high(self):
        ers = self._create_ers_instance(ExchangeRateService.IntervalType.ON, "24") # Max is 23 for 'ON' type hours
        with self.assertRaises(ValidationError) as cm:
            ers.full_clean()
        self.assertIn('fetch_interval', cm.exception.error_dict)

    def test_ers_interval_on_not_on_invalid_range_format(self):
        ers = self._create_ers_instance(ExchangeRateService.IntervalType.ON, "5-1")
        with self.assertRaises(ValidationError) as cm:
            ers.full_clean()
        self.assertIn('fetch_interval', cm.exception.error_dict)

    def test_ers_interval_on_not_on_invalid_range_value_too_high(self):
        ers = self._create_ers_instance(ExchangeRateService.IntervalType.ON, "20-24") # 24 is invalid hour
        with self.assertRaises(ValidationError) as cm:
            ers.full_clean()
        self.assertIn('fetch_interval', cm.exception.error_dict)

    def test_ers_interval_on_not_on_empty_interval(self):
        ers = self._create_ers_instance(ExchangeRateService.IntervalType.ON, "")
        with self.assertRaises(ValidationError) as cm:
            ers.full_clean()
        self.assertIn('fetch_interval', cm.exception.error_dict)

    @patch('apps.currencies.exchange_rates.fetcher.PROVIDER_MAPPING')
    def test_get_provider_valid_service_type(self, mock_provider_mapping):
        """Test get_provider returns a configured provider instance for a valid service_type."""

        class MockSynthFinanceProvider:
            def __init__(self, key):
                self.key = key

        # Configure the mock PROVIDER_MAPPING
        mock_provider_mapping.get.return_value = MockSynthFinanceProvider

        service_instance = self._create_ers_instance(
            interval_type=ExchangeRateService.IntervalType.EVERY, # Needs some valid interval type
            fetch_interval="1", # Needs some valid fetch interval
            service_type=ExchangeRateService.ServiceType.SYNTH_FINANCE,
            api_key="test_key"
        )
        # Ensure the service_type is correctly passed to the mock
        # The actual get_provider method uses PROVIDER_MAPPING[self.service_type]
        # So, we should make the mock_provider_mapping behave like a dict for the specific key
        mock_provider_mapping = {ExchangeRateService.ServiceType.SYNTH_FINANCE: MockSynthFinanceProvider}

        with patch('apps.currencies.exchange_rates.fetcher.PROVIDER_MAPPING', mock_provider_mapping):
            provider = service_instance.get_provider()

        self.assertIsInstance(provider, MockSynthFinanceProvider)
        self.assertEqual(provider.key, "test_key")

    @patch('apps.currencies.exchange_rates.fetcher.PROVIDER_MAPPING', {}) # Empty mapping
    def test_get_provider_invalid_service_type(self, mock_provider_mapping_empty):
        """Test get_provider raises KeyError for an invalid or unmapped service_type."""
        service_instance = self._create_ers_instance(
            interval_type=ExchangeRateService.IntervalType.EVERY,
            fetch_interval="1",
            service_type="UNMAPPED_SERVICE_TYPE", # A type not in the (mocked) mapping
            api_key="any_key"
        )

        with self.assertRaises(KeyError):
            service_instance.get_provider()


class ExchangeRateTests(TestCase):
    def setUp(self):
        """Set up test data"""
        self.usd = Currency.objects.create(
            code="USD", name="US Dollar", decimal_places=2, prefix="$ "
        )
        self.eur = Currency.objects.create(
            code="EUR", name="Euro", decimal_places=2, prefix="€ "
        )

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
        with self.assertRaises(IntegrityError):
            ExchangeRate.objects.create(
                from_currency=self.usd,
                to_currency=self.eur,
                rate=Decimal("0.86"),
                date=date,
            )

    def test_from_and_to_currency_cannot_be_same(self):
        """Test that from_currency and to_currency cannot be the same."""
        with self.assertRaises(ValidationError) as cm:
            rate = ExchangeRate(
                from_currency=self.usd,
                to_currency=self.usd,  # Same as from_currency
                rate=Decimal("1.00"),
                date=timezone.now().date(),
            )
            rate.full_clean()

        # Check if the error message is as expected or if the error is associated with a specific field.
        # The exact key ('to_currency' or '__all__') depends on how the model's clean() method is implemented.
        # Assuming the validation error is raised with a message like "From and to currency cannot be the same."
        # and is a non-field error or specifically tied to 'to_currency'.
        self.assertTrue(
            '__all__' in cm.exception.error_dict or 'to_currency' in cm.exception.error_dict,
            "ValidationError should be for '__all__' or 'to_currency'"
        )
        # Optionally, check for a specific message if it's consistent:
        # found_message = False
        # if '__all__' in cm.exception.error_dict:
        #     found_message = any("cannot be the same" in e.message for e in cm.exception.error_dict['__all__'])
        # if not found_message and 'to_currency' in cm.exception.error_dict:
        #     found_message = any("cannot be the same" in e.message for e in cm.exception.error_dict['to_currency'])
        # self.assertTrue(found_message, "Error message about currencies being the same not found.")


class CurrencyConversionUtilsTests(TestCase):
    def setUp(self):
        self.usd = Currency.objects.create(code="USD", name="US Dollar", decimal_places=2, prefix="$", suffix="")
        self.eur = Currency.objects.create(code="EUR", name="Euro", decimal_places=2, prefix="€", suffix="")
        self.gbp = Currency.objects.create(code="GBP", name="British Pound", decimal_places=2, prefix="£", suffix="")

        # Rates for USD <-> EUR
        self.usd_eur_rate_10th = ExchangeRate.objects.create(from_currency=self.usd, to_currency=self.eur, rate=Decimal("0.90"), date=date(2023, 1, 10))
        self.usd_eur_rate_15th = ExchangeRate.objects.create(from_currency=self.usd, to_currency=self.eur, rate=Decimal("0.92"), date=date(2023, 1, 15))
        ExchangeRate.objects.create(from_currency=self.usd, to_currency=self.eur, rate=Decimal("0.88"), date=date(2023, 1, 5))

        # Rate for GBP <-> USD (for inverse lookup)
        self.gbp_usd_rate_10th = ExchangeRate.objects.create(from_currency=self.gbp, to_currency=self.usd, rate=Decimal("1.25"), date=date(2023, 1, 10))

    def test_get_direct_rate_closest_date(self):
        """Test fetching a direct rate, ensuring the closest date is chosen."""
        result = get_exchange_rate(self.usd, self.eur, date(2023, 1, 16))
        self.assertIsNotNone(result)
        self.assertEqual(result.effective_rate, Decimal("0.92"))
        self.assertEqual(result.original_from_currency, self.usd)
        self.assertEqual(result.original_to_currency, self.eur)

    def test_get_inverse_rate_closest_date(self):
        """Test fetching an inverse rate, ensuring the closest date and correct calculation."""
        # We are looking for USD to GBP. We have GBP to USD on 2023-01-10.
        # Target date is 2023-01-12.
        result = get_exchange_rate(self.usd, self.gbp, date(2023, 1, 12))
        self.assertIsNotNone(result)
        self.assertEqual(result.effective_rate, Decimal("1") / self.gbp_usd_rate_10th.rate)
        self.assertEqual(result.original_from_currency, self.gbp) # original_from_currency should be GBP
        self.assertEqual(result.original_to_currency, self.usd)   # original_to_currency should be USD

    def test_get_rate_exact_date_preference(self):
        """Test that an exact date match is preferred over a closer one."""
        # Existing rate is on 2023-01-15 (0.92)
        # Add an exact match for the query date
        exact_date_rate = ExchangeRate.objects.create(from_currency=self.usd, to_currency=self.eur, rate=Decimal("0.91"), date=date(2023, 1, 16))

        result = get_exchange_rate(self.usd, self.eur, date(2023, 1, 16))
        self.assertIsNotNone(result)
        self.assertEqual(result.effective_rate, Decimal("0.91"))
        self.assertEqual(result.original_from_currency, self.usd)
        self.assertEqual(result.original_to_currency, self.eur)

    def test_get_rate_no_matching_pair(self):
        """Test that None is returned if no direct or inverse rate exists between the pair."""
        # No rates exist for EUR <-> GBP in the setUp
        result = get_exchange_rate(self.eur, self.gbp, date(2023, 1, 10))
        self.assertIsNone(result)

    def test_get_rate_prefer_direct_over_inverse_same_diff(self):
        """Test that a direct rate is preferred over an inverse if date differences are equal."""
        # We have GBP-USD on 2023-01-10 (self.gbp_usd_rate_10th)
        # This means an inverse USD-GBP rate is available for 2023-01-10.
        # Add a direct USD-GBP rate for the same date.
        direct_usd_gbp_rate = ExchangeRate.objects.create(from_currency=self.usd, to_currency=self.gbp, rate=Decimal("0.80"), date=date(2023, 1, 10))

        result = get_exchange_rate(self.usd, self.gbp, date(2023, 1, 10))
        self.assertIsNotNone(result)
        self.assertEqual(result.effective_rate, Decimal("0.80"))
        self.assertEqual(result.original_from_currency, self.usd)
        self.assertEqual(result.original_to_currency, self.gbp)

        # Now test the EUR to USD case from the problem description
        # Add EUR to USD, rate 1.1, date 2023-01-10
        eur_usd_direct_rate = ExchangeRate.objects.create(from_currency=self.eur, to_currency=self.usd, rate=Decimal("1.1"), date=date(2023, 1, 10))
        # We also have USD to EUR on 2023-01-10 (rate 0.90), which would be an inverse match for EUR to USD.

        result_eur_usd = get_exchange_rate(self.eur, self.usd, date(2023, 1, 10))
        self.assertIsNotNone(result_eur_usd)
        self.assertEqual(result_eur_usd.effective_rate, Decimal("1.1"))
        self.assertEqual(result_eur_usd.original_from_currency, self.eur)
        self.assertEqual(result_eur_usd.original_to_currency, self.usd)

    def test_convert_successful_direct(self):
        """Test successful conversion using a direct rate."""
        # Uses self.usd_eur_rate_15th (0.92) as it's closest to 2023-01-16
        converted_amount, prefix, suffix, dp = convert(Decimal('100'), self.usd, self.eur, date(2023, 1, 16))
        self.assertEqual(converted_amount, Decimal('92.00'))
        self.assertEqual(prefix, self.eur.prefix)
        self.assertEqual(suffix, self.eur.suffix)
        self.assertEqual(dp, self.eur.decimal_places)

    def test_convert_successful_inverse(self):
        """Test successful conversion using an inverse rate."""
        # Uses self.gbp_usd_rate_10th (GBP to USD @ 1.25), so USD to GBP is 1/1.25 = 0.8
        # Target date 2023-01-12, closest is 2023-01-10
        converted_amount, prefix, suffix, dp = convert(Decimal('100'), self.usd, self.gbp, date(2023, 1, 12))
        expected_amount = Decimal('100') * (Decimal('1') / self.gbp_usd_rate_10th.rate)
        self.assertEqual(converted_amount, expected_amount.quantize(Decimal('0.01')))
        self.assertEqual(prefix, self.gbp.prefix)
        self.assertEqual(suffix, self.gbp.suffix)
        self.assertEqual(dp, self.gbp.decimal_places)

    def test_convert_no_rate_found(self):
        """Test conversion when no exchange rate is found."""
        result_tuple = convert(Decimal('100'), self.eur, self.gbp, date(2023, 1, 10))
        self.assertEqual(result_tuple, (None, None, None, None))

    def test_convert_same_currency(self):
        """Test conversion when from_currency and to_currency are the same."""
        result_tuple = convert(Decimal('100'), self.usd, self.usd, date(2023, 1, 10))
        self.assertEqual(result_tuple, (None, None, None, None))

    def test_convert_zero_amount(self):
        """Test conversion when the amount is zero."""
        result_tuple = convert(Decimal('0'), self.usd, self.eur, date(2023, 1, 10))
        self.assertEqual(result_tuple, (None, None, None, None))

    @patch('apps.currencies.utils.convert.timezone')
    def test_convert_no_date_uses_today(self, mock_timezone):
        """Test conversion uses today's date when no date is provided."""
        # Mock timezone.now().date() to return a specific date
        mock_today = date(2023, 1, 16)
        mock_timezone.now.return_value.date.return_value = mock_today

        # This should use self.usd_eur_rate_15th (0.92) as it's closest to mocked "today" (2023-01-16)
        converted_amount, prefix, suffix, dp = convert(Decimal('100'), self.usd, self.eur)

        self.assertEqual(converted_amount, Decimal('92.00'))
        self.assertEqual(prefix, self.eur.prefix)
        self.assertEqual(suffix, self.eur.suffix)
        self.assertEqual(dp, self.eur.decimal_places)

        # Verify that timezone.now().date() was called (indirectly, by get_exchange_rate)
        # This specific assertion for get_exchange_rate being called with a specific date
        # would require patching get_exchange_rate itself, which is more complex.
        # For now, we rely on the correct outcome given the mocked date.
        # A more direct way to test date passing is if convert took get_exchange_rate as a dependency.
        mock_timezone.now.return_value.date.assert_called_once()
