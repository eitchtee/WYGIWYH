import json
import tempfile
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Account
from apps.currencies.models import Currency, ExchangeRate
from apps.transactions.models import Transaction


@override_settings(
    STATIC_ROOT=tempfile.gettempdir(),
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
)
class NetWorthCurrencyChartTests(TestCase):
    def test_consolidated_currency_is_a_selectable_dashed_matching_color_line(self):
        user = get_user_model().objects.create_user(
            email="chart@example.com", password="password"
        )
        usd = Currency.objects.create(code="USD", name="US Dollar", prefix="$ ")
        eur = Currency.objects.create(
            code="EUR", name="Euro", prefix="€ ", exchange_currency=usd
        )
        usd_account = Account.all_objects.create(
            name="USD account", currency=usd, owner=user
        )
        eur_account = Account.all_objects.create(
            name="EUR account", currency=eur, owner=user
        )
        ExchangeRate.objects.create(
            from_currency=eur,
            to_currency=usd,
            rate=Decimal("1.234567"),
            date=timezone.now(),
        )
        for account, amount in ((usd_account, "100"), (eur_account, "50")):
            Transaction.userless_all_objects.create(
                account=account,
                owner=user,
                type=Transaction.Type.INCOME,
                amount=Decimal(amount),
                date=date(2026, 1, 15),
                reference_date=date(2026, 1, 1),
                is_paid=True,
            )

        self.client.force_login(user)
        response = self.client.get(reverse("net_worth"))

        self.assertEqual(response.status_code, 200)
        chart_data = json.loads(response.context["chart_data_currency_json"])
        datasets = {dataset["label"]: dataset for dataset in chart_data["datasets"]}
        self.assertIn("US Dollar Consolidated", datasets)
        regular = datasets["US Dollar"]
        consolidated = datasets["US Dollar Consolidated"]
        self.assertEqual(consolidated["data"], [161.73])
        self.assertNotIn("borderColor", regular)
        self.assertNotIn("borderColor", consolidated)
        self.assertEqual(consolidated["colorSource"], "US Dollar")
        self.assertEqual(consolidated["borderDash"], [12, 6])
        self.assertEqual(consolidated["pointRadius"], 0)
        self.assertEqual(consolidated["pointHitRadius"], 8)
        self.assertContains(
            response,
            "showOnlyCurrencyDataset('US Dollar Consolidated', 'US Dollar')",
            html=False,
        )
        self.assertContains(
            response,
            '<span class="text-start shrink">Consolidated</span>',
            html=False,
        )
