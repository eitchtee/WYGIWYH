import re
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
        chart_data = response.context["chart_data_currency"]
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
            'data-dataset="US Dollar Consolidated" data-difference="US Dollar"',
            html=False,
        )
        self.assertContains(
            response,
            '<span class="text-start shrink">Consolidated</span>',
            html=False,
        )

    def test_consolidated_total_lists_each_currency_share(self):
        user = get_user_model().objects.create_user(
            email="shares@example.com", password="password"
        )
        usd = Currency.objects.create(code="USD", name="US Dollar", prefix="$ ")
        eur = Currency.objects.create(
            code="EUR", name="Euro", prefix="€ ", exchange_currency=usd
        )
        ExchangeRate.objects.create(
            from_currency=eur,
            to_currency=usd,
            rate=Decimal("2"),
            date=timezone.now(),
        )
        for currency, amount in ((usd, "300"), (eur, "50")):
            Transaction.userless_all_objects.create(
                account=Account.all_objects.create(
                    name=f"{currency.code} account", currency=currency, owner=user
                ),
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
        components = response.context["currency_net_worth"][usd.id]["consolidated"][
            "components"
        ]
        self.assertEqual(
            [(part["currency"]["name"], part["share"]) for part in components],
            [("US Dollar", Decimal("75")), ("Euro", Decimal("25"))],
        )
        self.assertContains(response, "75.0%")
        self.assertContains(response, "25.0%")


@override_settings(
    STATIC_ROOT=tempfile.gettempdir(),
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
)
class NetWorthChartEscapingTests(TestCase):
    def test_currency_and_account_names_cannot_break_out_of_the_chart_scripts(self):
        user = get_user_model().objects.create_user(
            email="xss@example.com", password="password"
        )
        payload = "</script><script>alert(1)</script>'"
        currency = Currency.objects.create(code="XSS", name=payload, prefix="$ ")
        account = Account.all_objects.create(
            name=payload, currency=currency, owner=user
        )
        Transaction.userless_all_objects.create(
            account=account,
            owner=user,
            type=Transaction.Type.INCOME,
            amount=Decimal("10"),
            date=date(2026, 1, 15),
            reference_date=date(2026, 1, 1),
            is_paid=True,
        )

        self.client.force_login(user)
        response = self.client.get(reverse("net_worth"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "<script>alert(1)")
        # Entities in an attribute are decoded before hyperscript parses it, so
        # names must never be interpolated into ``_="..."`` code.
        hyperscript = re.findall(r'\s_="([^"]*)"', response.content.decode())
        self.assertTrue(hyperscript)
        self.assertFalse([code for code in hyperscript if "alert(1)" in code])
