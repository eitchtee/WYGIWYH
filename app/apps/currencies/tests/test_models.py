from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from apps.currencies.models import Currency, ExchangeRate


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

    def test_currency_unique_name(self):
        """Test that currency names must be unique"""
        Currency.objects.create(code="USD", name="US Dollar", decimal_places=2)
        with self.assertRaises(IntegrityError):
            Currency.objects.create(code="USD2", name="US Dollar", decimal_places=2)


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
        with self.assertRaises(Exception):  # Could be IntegrityError
            ExchangeRate.objects.create(
                from_currency=self.usd,
                to_currency=self.eur,
                rate=Decimal("0.86"),
                date=date,
            )
