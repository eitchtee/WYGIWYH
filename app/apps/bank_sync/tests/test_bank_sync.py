import io
import os
import zipfile
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Account
from apps.bank_sync.forms import BankSyncAccountForm, BankSyncServiceForm
from apps.bank_sync.models import BankSyncAccount, BankSyncService
from apps.bank_sync.providers.base import RemoteAccount, RemoteTransaction
from apps.bank_sync.providers.lunchflow import LunchFlowProvider
from apps.bank_sync.sync import is_due, refresh_remote_accounts, sync_service
from apps.common.middleware.thread_local import delete_current_user, write_current_user
from apps.currencies.models import Currency
from apps.transactions.models import Transaction


def _response(payload):
    response = MagicMock()
    response.json.return_value = payload
    return response


class LunchFlowProviderTests(TestCase):
    def setUp(self):
        # Independent of whatever the test machine has set
        self.enterContext(patch.dict("os.environ"))
        os.environ.pop("LUNCHFLOW_API_URL", None)
        self.provider = LunchFlowProvider({"api_key": "key"})

    def test_sends_api_key_and_uses_default_url(self):
        self.assertEqual(self.provider.session.headers["x-api-key"], "key")
        self.assertEqual(self.provider.base_url, "https://www.lunchflow.app/api/v1")

    def test_url_comes_from_the_environment_not_settings(self):
        with patch.dict("os.environ", {"LUNCHFLOW_API_URL": "https://x.test/v1/"}):
            provider = LunchFlowProvider({"api_key": "k", "base_url": "http://db:5432"})
        self.assertEqual(provider.base_url, "https://x.test/v1")

    def test_list_accounts(self):
        def get(url, **kwargs):
            if url.endswith("/accounts"):
                return _response(
                    {
                        "accounts": [
                            {"id": 7, "name": "Checking", "institution_name": "Bank", "status": "ACTIVE"},
                            {"id": 8, "name": "Card", "institution_name": None, "status": "EXPIRED"},
                        ]
                    }
                )
            if url.endswith("/7/balance"):
                return _response({"balance": {"amount": 1, "currency": "eur"}})
            raise __import__("requests").HTTPError("expired")

        with patch.object(self.provider.session, "get", side_effect=get):
            accounts = self.provider.list_accounts()

        self.assertEqual(accounts[0], RemoteAccount("7", "Bank - Checking", ("EUR",), ""))
        self.assertEqual(accounts[1].name, "Card")
        self.assertEqual(accounts[1].currencies, ())
        self.assertIn("EXPIRED", accounts[1].error)

    def test_get_transactions(self):
        payload = {
            "transactions": [
                {"id": "a", "amount": -12.5, "currency": "EUR", "date": "2026-10-01", "merchant": "Coffee", "description": "CARD 123 COFFEE", "isPending": False},
                {"id": "b", "amount": 1000, "currency": "usd", "date": "2026-10-02", "merchant": None, "description": "Salary"},
                {"id": "c", "amount": -1, "date": "2026-10-03", "merchant": "Pending", "isPending": True},
                {"id": "d", "amount": -3, "date": "2026-10-04", "merchant": "Same", "description": "Same"},
            ]
        }
        with patch.object(
            self.provider.session, "get", return_value=_response(payload)
        ) as mock_get:
            transactions = self.provider.get_transactions("7", date(2026, 10, 1))

        mock_get.assert_called_once_with(
            "https://www.lunchflow.app/api/v1/accounts/7/transactions",
            params={"from": "2026-10-01"},
            timeout=30,
        )
        self.assertEqual(
            transactions,
            [
                RemoteTransaction("a", date(2026, 10, 1), Decimal("-12.5"), "Coffee", "CARD 123 COFFEE", "EUR"),
                RemoteTransaction("b", date(2026, 10, 2), Decimal("1000"), "Salary", "", "USD"),
                RemoteTransaction("d", date(2026, 10, 4), Decimal("-3"), "Same", "", ""),
            ],
        )


class FakeProvider:
    def __init__(self, transactions=(), accounts=()):
        self.transactions = list(transactions)
        self.accounts = list(accounts)
        self.calls = []

    def list_accounts(self):
        return self.accounts

    def get_transactions(self, account_id, start_date):
        self.calls.append((account_id, start_date))
        return [t for t in self.transactions if t.date >= start_date]


class SyncTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="sync@example.com", password="x"
        )
        self.eur = Currency.objects.create(code="EUR", name="Euro", decimal_places=2)
        self.account = Account.objects.create(
            name="Checking", currency=self.eur, owner=self.user
        )
        self.service = BankSyncService.objects.create(
            name="LF", service_type="lunchflow", owner=self.user
        )
        self.link = BankSyncAccount.objects.create(
            service=self.service,
            external_id="7",
            account=self.account,
            start_date=date(2026, 10, 1),
        )
        self.provider = FakeProvider(
            [
                RemoteTransaction("old", date(2026, 9, 30), Decimal("-1"), "Before start"),
                RemoteTransaction("a", date(2026, 10, 1), Decimal("-12.555"), "Coffee", "note", "EUR"),
                RemoteTransaction("b", date(2026, 10, 2), Decimal("1000"), "Salary", "", "EUR"),
            ],
            accounts=[RemoteAccount("7", "Bank - Checking", ("EUR",))],
        )

    def _sync(self):
        with patch.object(BankSyncService, "get_provider", return_value=self.provider):
            created = sync_service(self.service)
        self.service.refresh_from_db()
        self.link.refresh_from_db()
        return created

    def test_creates_transactions(self):
        self.assertEqual(self._sync(), 2)

        coffee = Transaction.userless_all_objects.get(internal_id="lunchflow:7:a")
        self.assertEqual(coffee.type, Transaction.Type.EXPENSE)
        self.assertEqual(coffee.amount, Decimal("12.55"))  # truncated to currency
        self.assertEqual(coffee.description, "Coffee")
        self.assertEqual(coffee.notes, "note")
        self.assertEqual(coffee.owner, self.user)
        self.assertEqual(coffee.account, self.account)
        self.assertTrue(coffee.is_paid)

        salary = Transaction.userless_all_objects.get(internal_id="lunchflow:7:b")
        self.assertEqual(salary.type, Transaction.Type.INCOME)
        self.assertEqual(salary.amount, Decimal("1000"))

        self.assertIsNotNone(self.service.last_sync)
        self.assertEqual(self.link.last_synced_date, timezone.localdate())
        self.assertEqual(self.link.external_name, "Bank - Checking")

    def test_second_run_does_not_duplicate(self):
        self._sync()
        self.assertEqual(self._sync(), 0)
        self.assertEqual(Transaction.userless_all_objects.count(), 2)

    def test_deleted_transactions_are_not_reimported(self):
        self._sync()
        Transaction.userless_all_objects.filter(internal_id="lunchflow:7:a").update(
            deleted=True
        )
        self.assertEqual(self._sync(), 0)

    def test_later_runs_only_look_back_the_overlap(self):
        self.link.last_synced_date = date(2026, 11, 1)
        self.link.save()
        self._sync()
        self.assertEqual(self.provider.calls, [("7", date(2026, 10, 25))])

    def test_unlinked_accounts_are_skipped(self):
        self.link.account = None
        self.link.save()
        self.assertEqual(self._sync(), 0)
        self.assertEqual(self.provider.calls, [])

    def test_currency_filter(self):
        self.provider.transactions.append(
            RemoteTransaction("usd", date(2026, 10, 3), Decimal("-5"), "Abroad", "", "USD")
        )
        self.link.currencies = ["USD"]
        self.link.save()
        self.assertEqual(self._sync(), 1)
        self.assertTrue(
            Transaction.userless_all_objects.filter(internal_id="lunchflow:7:usd").exists()
        )
        # Every currency seen becomes a choice, even filtered out ones
        self.assertEqual(self.link.available_currencies, ["EUR", "USD"])

    def test_no_currency_filter_syncs_all(self):
        self.provider.transactions.append(
            RemoteTransaction("usd", date(2026, 10, 3), Decimal("-5"), "Abroad", "", "USD")
        )
        self.assertEqual(self._sync(), 3)

    def test_match_existing_is_off_by_default(self):
        Transaction.objects.create(
            account=self.account, owner=self.user, type=Transaction.Type.INCOME,
            amount=Decimal("1000"), date=date(2026, 10, 2), description="Mine",
        )
        self.assertEqual(self._sync(), 2)

    @patch("apps.rules.signals.check_for_transaction_rules.defer")
    def test_matching_does_not_trigger_rules(self, defer):
        self.service.match_existing = True
        self.service.save()
        self.provider.transactions = self.provider.transactions[2:]  # salary only
        Transaction.objects.create(
            account=self.account, owner=self.user, type=Transaction.Type.INCOME,
            amount=Decimal("1000"), date=date(2026, 10, 2), description="Mine",
        )
        defer.reset_mock()
        self.assertEqual(self._sync(), 0)
        defer.assert_not_called()

    def test_match_existing(self):
        self.service.match_existing = True
        self.service.save()
        far = Transaction.objects.create(
            account=self.account, owner=self.user, type=Transaction.Type.INCOME,
            amount=Decimal("1000"), date=date(2026, 9, 28), description="Too far",
        )
        close = Transaction.objects.create(
            account=self.account, owner=self.user, type=Transaction.Type.INCOME,
            amount=Decimal("1000"), date=date(2026, 10, 3), description="Mine",
        )
        expense = Transaction.objects.create(
            account=self.account, owner=self.user, type=Transaction.Type.EXPENSE,
            amount=Decimal("12.55"), date=date(2026, 10, 1), description="Coffee by hand",
        )

        self.assertEqual(self._sync(), 0)
        close.refresh_from_db()
        expense.refresh_from_db()
        far.refresh_from_db()
        self.assertEqual(close.internal_id, "lunchflow:7:b")
        self.assertEqual(close.description, "Mine")  # left as the user wrote it
        self.assertEqual(expense.internal_id, "lunchflow:7:a")
        self.assertIsNone(far.internal_id)
        # Matched once, never again
        self.assertEqual(self._sync(), 0)

    def test_match_existing_takes_one_per_synced_transaction(self):
        self.service.match_existing = True
        self.service.save()
        self.provider.transactions = [
            RemoteTransaction("x1", date(2026, 10, 5), Decimal("-3"), "Coffee", "", "EUR"),
            RemoteTransaction("x2", date(2026, 10, 5), Decimal("-3"), "Coffee", "", "EUR"),
        ]
        Transaction.objects.create(
            account=self.account, owner=self.user, type=Transaction.Type.EXPENSE,
            amount=Decimal("3"), date=date(2026, 10, 5), description="One coffee",
        )
        self.assertEqual(self._sync(), 1)
        self.assertEqual(Transaction.userless_all_objects.count(), 2)

    def test_failing_account_does_not_stop_the_others(self):
        other = Account.objects.create(name="Other", currency=self.eur, owner=self.user)
        other_link = BankSyncAccount.objects.create(
            service=self.service, external_id="8", account=other, start_date=date(2026, 10, 1)
        )
        self.provider.accounts.append(RemoteAccount("8", "Broken"))
        get_transactions = self.provider.get_transactions

        def flaky(account_id, start_date):
            if account_id == "8":
                raise Exception("boom")
            return get_transactions(account_id, start_date)

        self.provider.get_transactions = flaky
        self.assertEqual(self._sync(), 2)
        other_link.refresh_from_db()
        self.assertEqual(other_link.last_error, "boom")
        self.assertEqual(self.link.last_error, "")
        self.assertEqual(self.service.failure_count, 1)
        self.assertIn("boom", self.service.last_error)
        self.assertIsNone(self.service.last_sync)  # retried next run

        self.provider.get_transactions = get_transactions
        self._sync()
        other_link.refresh_from_db()
        self.assertEqual(other_link.last_error, "")
        self.assertEqual(self.service.failure_count, 0)
        self.assertEqual(self.service.last_error, "")
        self.assertIsNotNone(self.service.last_sync)

    def test_provider_reported_problem_skips_the_account(self):
        self.provider.accounts = [RemoteAccount("7", "Bank", (), "Connection expired")]
        self.assertEqual(self._sync(), 0)
        self.assertEqual(self.provider.calls, [])
        self.assertEqual(self.link.remote_error, "Connection expired")
        self.assertEqual(self.link.last_error, "Connection expired")
        self.assertEqual(self.service.failure_count, 1)

    def test_listing_failure_is_recorded(self):
        self.provider.list_accounts = MagicMock(side_effect=Exception("401"))
        self.assertEqual(self._sync(), 0)
        self.assertEqual(self.service.failure_count, 1)
        self.assertEqual(self.service.last_error, "401")
        self.assertTrue(BankSyncAccount.objects.filter(pk=self.link.pk).exists())

    @patch("apps.rules.signals.check_for_transaction_rules.defer")
    def test_rules_are_triggered(self, defer):
        self._sync()
        self.assertEqual(defer.call_count, 2)
        self.assertEqual(defer.call_args.kwargs["user_id"], self.user.id)

    @patch("apps.rules.signals.check_for_transaction_rules.defer")
    def test_rules_can_be_disabled(self, defer):
        self.service.trigger_rules = False
        self.service.save()
        self._sync()
        defer.assert_not_called()

    def test_refresh_remote_accounts(self):
        self.link.available_currencies = ["GBP"]
        self.link.save()
        gone = BankSyncAccount.objects.create(service=self.service, external_id="gone")
        self.provider.accounts = [
            RemoteAccount("7", "Renamed", ("EUR",)),
            RemoteAccount("9", "New", ("USD",)),
        ]
        refresh_remote_accounts(self.service, self.provider)

        self.link.refresh_from_db()
        self.assertEqual(self.link.external_name, "Renamed")
        self.assertEqual(self.link.account, self.account)
        self.assertEqual(self.link.available_currencies, ["EUR", "GBP"])
        self.assertTrue(self.service.accounts.filter(external_id="9", account=None).exists())
        self.assertFalse(BankSyncAccount.objects.filter(pk=gone.pk).exists())

    def test_is_due(self):
        self.service.sync_interval = 24
        self.assertTrue(is_due(self.service))
        self.service.last_sync = timezone.now() - timedelta(hours=23)
        self.assertFalse(is_due(self.service))
        self.service.last_sync = timezone.now() - timedelta(hours=25)
        self.assertTrue(is_due(self.service))


class FormTests(TestCase):
    def setUp(self):
        # Account choices are scoped to the logged in user
        self.user = get_user_model().objects.create_user(email="f@example.com", password="x")
        write_current_user(self.user)
        self.addCleanup(delete_current_user)

    def test_provider_settings_fields_are_added(self):
        form = BankSyncServiceForm(initial={"service_type": "lunchflow"})
        self.assertIn("setting_api_key", form.fields)
        self.assertNotIn("setting_base_url", form.fields)
        self.assertNotIn("setting_api_key", BankSyncServiceForm().fields)

    def test_settings_are_saved_and_loaded(self):
        form = BankSyncServiceForm(
            {
                "name": "LF",
                "service_type": "lunchflow",
                "is_active": "on",
                "sync_interval": "24",
                "setting_api_key": "secret",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        service = form.save()
        self.assertEqual(service.settings, {"api_key": "secret"})

        edit = BankSyncServiceForm(instance=service)
        self.assertEqual(edit.initial["setting_api_key"], "secret")

    def test_service_type_is_locked_on_edit(self):
        service = BankSyncService.objects.create(
            name="LF", service_type="lunchflow", settings={"api_key": "k"}
        )
        form = BankSyncServiceForm(
            {"name": "LF", "service_type": "other", "sync_interval": "24", "setting_api_key": "k"},
            instance=service,
        )
        self.assertTrue(form.fields["service_type"].disabled)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().service_type, "lunchflow")

    def test_provider_settings_are_validated(self):
        form = BankSyncServiceForm(
            {"name": "LF", "service_type": "lunchflow", "sync_interval": "24"}
        )
        self.assertFalse(form.is_valid())
        self.assertIn("setting_api_key", form.errors)

    def test_account_link_form(self):
        eur = Currency.objects.create(code="€", name="Euro")
        service = BankSyncService.objects.create(name="LF", service_type="lunchflow")
        link = BankSyncAccount.objects.create(
            service=service, external_id="7", available_currencies=["EUR", "USD"]
        )
        account = Account.objects.create(name="EUR", currency=eur, owner=self.user)

        form = BankSyncAccountForm({"account": account.id}, instance=link)
        self.assertFalse(form.is_valid())
        self.assertIn("start_date", form.errors)

        # Currency codes don't need to match: WYGIWYH's are free form
        form = BankSyncAccountForm(
            {"account": account.id, "start_date": "2026-10-01", "currencies": ["USD"]},
            instance=link,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().currencies, ["USD"])

        form = BankSyncAccountForm({"currencies": ["GBP"]}, instance=link)
        self.assertIn("currencies", form.errors)

        self.assertTrue(BankSyncAccountForm({}, instance=link).is_valid())

    def test_linked_archived_account_stays_valid(self):
        eur = Currency.objects.create(code="EUR", name="Euro")
        service = BankSyncService.objects.create(name="LF", service_type="lunchflow")
        archived = Account.objects.create(name="Old", currency=eur, owner=self.user, is_archived=True)
        other_archived = Account.objects.create(name="Older", currency=eur, owner=self.user, is_archived=True)
        link = BankSyncAccount.objects.create(
            service=service, external_id="7", account=archived, start_date=date(2026, 10, 1)
        )
        form = BankSyncAccountForm(
            {"account": archived.id, "start_date": "2026-10-01"}, instance=link
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertNotIn(other_archived, form.fields["account"].queryset)


class ViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            email="admin@example.com", password="x"
        )
        self.client.force_login(self.user)
        self.htmx = {"HTTP_HX_REQUEST": "true"}

    def test_switching_provider_renders_its_fields(self):
        response = self.client.get(
            reverse("bank_sync_add"), {"service_type": "lunchflow", "name": "Typed"}, **self.htmx
        )
        self.assertContains(response, 'name="setting_api_key"')
        self.assertContains(response, 'value="Typed"')

    def test_add_and_map_accounts(self):
        response = self.client.post(
            reverse("bank_sync_add"),
            {"name": "LF", "service_type": "lunchflow", "sync_interval": "24", "setting_api_key": "k"},
            **self.htmx,
        )
        self.assertEqual(response.status_code, 204)
        service = BankSyncService.objects.get()
        self.assertEqual(service.owner, self.user)

        provider = FakeProvider(
            accounts=[
                RemoteAccount("7", "Bank - Checking", ("EUR",)),
                RemoteAccount("8", "Card", (), "Connection expired"),
            ]
        )
        with patch.object(BankSyncService, "get_provider", return_value=provider):
            response = self.client.get(reverse("bank_sync_accounts", args=[service.id]), **self.htmx)
        self.assertContains(response, "Bank - Checking")
        self.assertContains(response, "Connection expired")
        self.assertContains(response, 'value="EUR"')

        account = Account.objects.create(
            name="Checking", currency=Currency.objects.create(code="EUR", name="Euro")
        )
        link = service.accounts.get(external_id="7")
        card = service.accounts.get(external_id="8")
        response = self.client.post(
            reverse("bank_sync_accounts", args=[service.id]),
            {
                "form-TOTAL_FORMS": "2",
                "form-INITIAL_FORMS": "2",
                "form-0-id": card.id,
                "form-1-id": link.id,
                "form-1-account": account.id,
                "form-1-start_date": "2026-10-01",
                "form-1-currencies": "EUR",
            },
            **self.htmx,
        )
        self.assertEqual(response.status_code, 204)
        link.refresh_from_db()
        self.assertEqual(link.account, account)
        self.assertEqual(link.currencies, ["EUR"])

    def test_accounts_view_shows_provider_errors(self):
        service = BankSyncService.objects.create(name="LF", service_type="lunchflow")
        with patch.object(BankSyncService, "get_provider", side_effect=Exception("401")):
            response = self.client.get(reverse("bank_sync_accounts", args=[service.id]), **self.htmx)
        self.assertContains(response, "401")

    def test_other_users_services_are_hidden(self):
        other = get_user_model().objects.create_user(email="o@example.com", password="x")
        service = BankSyncService.objects.create(name="LF", service_type="lunchflow", owner=other)
        response = self.client.get(reverse("bank_sync_edit", args=[service.id]), **self.htmx)
        self.assertEqual(response.status_code, 404)


class ExportRestoreTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            email="admin@example.com", password="x"
        )
        self.other = get_user_model().objects.create_user(
            email="other@example.com", password="x"
        )
        self.client.force_login(self.admin)
        eur = Currency.objects.create(code="EUR", name="Euro")
        # Same name for both users: links must not mix them up
        self.account = Account.objects.create(name="Checking", currency=eur, owner=self.other)
        Account.objects.create(name="Checking", currency=eur, owner=self.admin)
        self.service = BankSyncService.objects.create(
            name="LF",
            service_type="lunchflow",
            owner=self.other,
            settings={"api_key": "secret"},
            sync_interval=12,
            trigger_rules=False,
            match_existing=True,
        )
        BankSyncAccount.objects.create(
            service=self.service,
            external_id="7",
            external_name="Bank - Checking",
            available_currencies=["EUR", "USD"],
            currencies=["EUR"],
            account=self.account,
            start_date=date(2026, 10, 1),
            last_synced_date=date(2026, 11, 1),
        )
        BankSyncAccount.objects.create(service=self.service, external_id="8")

    def test_round_trip(self):
        response = self.client.post(
            reverse("export_form"),
            {"users": "on", "accounts": "on", "currencies": "on", "bank_sync": "on"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response["Content-Type"], "application/zip")
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            self.assertIn("bank_sync_services.csv", z.namelist())
            self.assertIn("bank_sync_accounts.csv", z.namelist())

        BankSyncService._base_manager.all().delete()

        upload = SimpleUploadedFile("export.zip", response.content)
        response = self.client.post(
            reverse("restore_form"), {"zip_file": upload}, HTTP_HX_REQUEST="true"
        )
        self.assertEqual(response.status_code, 204)

        service = BankSyncService._base_manager.get()
        self.assertEqual(service.owner, self.other)
        self.assertEqual(service.settings, {"api_key": "secret"})
        self.assertEqual(service.sync_interval, 12)
        self.assertFalse(service.trigger_rules)
        self.assertTrue(service.match_existing)

        linked = service.accounts.get(external_id="7")
        self.assertEqual(linked.account, self.account)
        self.assertEqual(linked.start_date, date(2026, 10, 1))
        self.assertEqual(linked.last_synced_date, date(2026, 11, 1))
        self.assertEqual(linked.available_currencies, ["EUR", "USD"])
        self.assertEqual(linked.currencies, ["EUR"])
        self.assertIsNone(service.accounts.get(external_id="8").account)
