from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Account, AccountGroup
from apps.common.middleware.thread_local import delete_current_user, write_current_user
from apps.currencies.models import Currency, ExchangeRate
from apps.mini_tools.utils.simulator import get_simulator_baseline
from apps.transactions.models import Transaction


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
    WHITENOISE_AUTOREFRESH=True,
)
@patch(
    "apps.mini_tools.utils.simulator.timezone.localdate",
    return_value=date(2026, 3, 15),
)
class SimulatorTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            email="testuser@test.com", password="testpass123"
        )
        self.client.login(username="testuser@test.com", password="testpass123")
        write_current_user(self.user)

        self.currency = Currency.objects.create(
            code="USD", name="US Dollar", decimal_places=2, prefix="$ "
        )
        group = AccountGroup.objects.create(name="Group")
        self.account = Account.objects.create(
            name="Checking", group=group, currency=self.currency
        )

    def tearDown(self):
        delete_current_user()

    def _transaction(self, type, amount, reference_date, is_paid=True, account=None):
        return Transaction.objects.create(
            account=account or self.account,
            type=type,
            is_paid=is_paid,
            date=reference_date,
            reference_date=reference_date,
            amount=Decimal(amount),
            description="Test",
            owner=self.user,
        )

    def _currency(self, baseline):
        return next(c for c in baseline["currencies"] if c["id"] == self.currency.id)

    def test_baseline_monthly_projection(self, _):
        self._transaction(Transaction.Type.INCOME, "1000", date(2026, 1, 1))
        self._transaction(Transaction.Type.EXPENSE, "200", date(2026, 2, 1), False)
        self._transaction(Transaction.Type.INCOME, "500", date(2026, 3, 1), False)
        self._transaction(Transaction.Type.EXPENSE, "50", date(2026, 3, 1))
        self._transaction(Transaction.Type.EXPENSE, "100", date(2031, 5, 1), False)

        baseline = get_simulator_baseline(self.user)
        currency = self._currency(baseline)

        self.assertEqual(baseline["current_month"], "2026-03")
        self.assertEqual(
            currency["monthly"],
            {"2026-01": 1000.0, "2026-02": -200.0, "2026-03": 450.0, "2031-05": -100.0},
        )
        self.assertIsNone(currency["exchange"])

    def test_baseline_ignores_archived_and_untracked_accounts(self, _):
        group = AccountGroup.objects.create(name="Other")
        archived = Account.objects.create(
            name="Old", group=group, currency=self.currency, is_archived=True
        )
        untracked = Account.objects.create(
            name="Hidden", group=group, currency=self.currency
        )
        untracked.untracked_by.add(self.user)

        self._transaction(Transaction.Type.INCOME, "100", date(2026, 3, 1))
        self._transaction(
            Transaction.Type.INCOME, "1000", date(2026, 3, 1), account=archived
        )
        self._transaction(
            Transaction.Type.INCOME, "1000", date(2026, 3, 1), account=untracked
        )

        currency = self._currency(get_simulator_baseline(self.user))

        self.assertEqual(currency["monthly"], {"2026-03": 100.0})

    def test_baseline_exchange_rate(self, _):
        euro = Currency.objects.create(
            code="EUR", name="Euro", decimal_places=2, suffix=" EUR"
        )
        self.currency.exchange_currency = euro
        self.currency.save()
        ExchangeRate.objects.create(
            from_currency=self.currency,
            to_currency=euro,
            rate=Decimal("0.5"),
            date=timezone.now(),
        )

        currency = self._currency(get_simulator_baseline(self.user))

        self.assertEqual(
            currency["exchange"],
            {"rate": 0.5, "prefix": "", "suffix": " EUR", "decimal_places": 2},
        )

    def test_simulator_view_renders(self, _):
        response = self.client.get(reverse("simulator"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="simulator-baseline"')
        self.assertContains(response, "sim-start")
