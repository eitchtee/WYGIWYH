from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from unittest.mock import patch
from decimal import Decimal
from datetime import date
from django.test import Client # Added
from django.urls import reverse # Added

from apps.currencies.models import Currency, ExchangeRate
from apps.mini_tools.utils.exchange_rate_map import get_currency_exchange_map

class MiniToolsUtilsTests(TestCase):
    def setUp(self):
        # User is not strictly necessary for this utility but good practice for test setup
        self.user = User.objects.create_user(username='testuser', password='password')

        self.usd = Currency.objects.create(name="US Dollar", code="USD", decimal_places=2, prefix="$")
        self.eur = Currency.objects.create(name="Euro", code="EUR", decimal_places=2, prefix="€")
        self.gbp = Currency.objects.create(name="British Pound", code="GBP", decimal_places=2, prefix="£")

        # USD -> EUR rates
        # Rate for 2023-01-10 (will be processed last for USD->EUR due to ordering)
        ExchangeRate.objects.create(from_currency=self.usd, to_currency=self.eur, rate=Decimal("0.90"), date=date(2023, 1, 10))
        # Rate for 2023-01-15 (closer to target_date 2023-01-16, processed first for USD->EUR)
        ExchangeRate.objects.create(from_currency=self.usd, to_currency=self.eur, rate=Decimal("0.92"), date=date(2023, 1, 15))

        # GBP -> USD rate
        self.gbp_usd_rate = ExchangeRate.objects.create(from_currency=self.gbp, to_currency=self.usd, rate=Decimal("1.25"), date=date(2023, 1, 12))

    def test_get_currency_exchange_map_structure_and_rates(self):
        target_date = date(2023, 1, 16)
        rate_map = get_currency_exchange_map(date=target_date)

        # Assert USD in map
        self.assertIn("US Dollar", rate_map)
        usd_data = rate_map["US Dollar"]
        self.assertEqual(usd_data["decimal_places"], 2)
        self.assertEqual(usd_data["prefix"], "$")
        self.assertIn("rates", usd_data)

        # USD -> EUR: Expecting rate from 2023-01-10 (0.90)
        # Query order: (USD,EUR,2023-01-15), (USD,EUR,2023-01-10)
        # Loop overwrite means the last one processed (0.90) sticks.
        self.assertIn("Euro", usd_data["rates"])
        self.assertEqual(usd_data["rates"]["Euro"]["rate"], Decimal("0.90"))

        # USD -> GBP: Inverse of GBP->USD rate from 2023-01-12 (1.25)
        # Query for GBP->USD, date 2023-01-12, diff 4 days.
        self.assertIn("British Pound", usd_data["rates"])
        self.assertEqual(usd_data["rates"]["British Pound"]["rate"], Decimal("1") / self.gbp_usd_rate.rate)

        # Assert EUR in map
        self.assertIn("Euro", rate_map)
        eur_data = rate_map["Euro"]
        self.assertEqual(eur_data["decimal_places"], 2)
        self.assertEqual(eur_data["prefix"], "€")
        self.assertIn("rates", eur_data)

        # EUR -> USD: Inverse of USD->EUR rate from 2023-01-10 (0.90)
        self.assertIn("US Dollar", eur_data["rates"])
        self.assertEqual(eur_data["rates"]["US Dollar"]["rate"], Decimal("1") / Decimal("0.90"))

        # Assert GBP in map
        self.assertIn("British Pound", rate_map)
        gbp_data = rate_map["British Pound"]
        self.assertEqual(gbp_data["decimal_places"], 2)
        self.assertEqual(gbp_data["prefix"], "£")
        self.assertIn("rates", gbp_data)

        # GBP -> USD: Direct rate from 2023-01-12 (1.25)
        self.assertIn("US Dollar", gbp_data["rates"])
        self.assertEqual(gbp_data["rates"]["US Dollar"]["rate"], self.gbp_usd_rate.rate)

    @patch('apps.mini_tools.utils.exchange_rate_map.timezone')
    def test_get_currency_exchange_map_uses_today_if_no_date(self, mock_django_timezone):
        # Mock timezone.localtime().date() to return a specific date
        mock_today = date(2023, 1, 16)
        mock_django_timezone.localtime.return_value.date.return_value = mock_today

        rate_map = get_currency_exchange_map() # No date argument, should use mocked "today"

        # Re-assert one key rate to confirm the mocked date was used.
        # Based on test_get_currency_exchange_map_structure_and_rates, with target_date 2023-01-16,
        # USD -> EUR should be 0.90.
        self.assertIn("US Dollar", rate_map)
        self.assertIn("Euro", rate_map["US Dollar"]["rates"])
        self.assertEqual(rate_map["US Dollar"]["rates"]["Euro"]["rate"], Decimal("0.90"))

        # Verify that timezone.localtime().date() was called
        mock_django_timezone.localtime.return_value.date.assert_called_once()


class MiniToolsViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='viewtestuser', password='password')
        self.client = Client()
        self.client.login(username='viewtestuser', password='password')

        self.usd = Currency.objects.create(name="US Dollar Test", code="USDTEST", decimal_places=2, prefix="$T ")
        self.eur = Currency.objects.create(name="Euro Test", code="EURTEST", decimal_places=2, prefix="€T ")

    @patch('apps.mini_tools.views.convert')
    def test_currency_converter_convert_view_successful(self, mock_convert):
        mock_convert.return_value = (Decimal("85.00"), "€T ", "", 2) # prefix, suffix, dp

        get_params = {
            'from_value': "100",
            'from_currency': self.usd.id,
            'to_currency': self.eur.id
        }
        response = self.client.get(reverse('mini_tools:currency_converter_convert'), data=get_params)

        self.assertEqual(response.status_code, 200)

        mock_convert.assert_called_once()
        args, kwargs = mock_convert.call_args

        # The view calls: convert(amount=amount_decimal, from_currency=from_currency_obj, to_currency=to_currency_obj)
        # So, these are keyword arguments.
        self.assertEqual(kwargs['amount'], Decimal('100'))
        self.assertEqual(kwargs['from_currency'], self.usd)
        self.assertEqual(kwargs['to_currency'], self.eur)

        self.assertEqual(response.context['converted_amount'], Decimal("85.00"))
        self.assertEqual(response.context['prefix'], "€T ")
        self.assertEqual(response.context['suffix'], "")
        self.assertEqual(response.context['decimal_places'], 2)
        self.assertEqual(response.context['from_value'], "100") # Check original value passed through
        self.assertEqual(response.context['from_currency_selected'], str(self.usd.id))
        self.assertEqual(response.context['to_currency_selected'], str(self.eur.id))


    @patch('apps.mini_tools.views.convert')
    def test_currency_converter_convert_view_missing_params(self, mock_convert):
        get_params = {
            'from_value': "100",
            'from_currency': self.usd.id
            # 'to_currency' is missing
        }
        response = self.client.get(reverse('mini_tools:currency_converter_convert'), data=get_params)

        self.assertEqual(response.status_code, 200)
        mock_convert.assert_not_called()
        self.assertIsNone(response.context.get('converted_amount')) # Use .get() for safety if key might be absent
        self.assertEqual(response.context['from_value'], "100")
        self.assertEqual(response.context['from_currency_selected'], str(self.usd.id))
        self.assertIsNone(response.context.get('to_currency_selected'))


    @patch('apps.mini_tools.views.convert')
    def test_currency_converter_convert_view_invalid_currency_id(self, mock_convert):
        get_params = {
            'from_value': "100",
            'from_currency': self.usd.id,
            'to_currency': 999 # Non-existent currency ID
        }
        response = self.client.get(reverse('mini_tools:currency_converter_convert'), data=get_params)

        self.assertEqual(response.status_code, 200)
        mock_convert.assert_not_called()
        self.assertIsNone(response.context.get('converted_amount'))
        self.assertEqual(response.context['from_value'], "100")
        self.assertEqual(response.context['from_currency_selected'], str(self.usd.id))
        self.assertEqual(response.context['to_currency_selected'], '999') # View passes invalid ID to context
