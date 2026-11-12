"""Tests for importing a file into an account picked for the import run."""

import shutil
import tempfile
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.common.middleware.thread_local import delete_current_user, write_current_user
from apps.currencies.models import Currency
from apps.import_app.models import ImportProfile, ImportRun
from apps.import_app.services.v1 import ImportService
from apps.import_app.tests.test_view_permissions import (
    HTMX,
    ImportObjectPermissionTestCase,
)
from apps.transactions.models import Transaction

CSV_SETTINGS = """
settings:
  file_type: csv
  importing: transactions
  trigger_transaction_rules: false
"""

CSV_MAPPING = """
mapping:
  date:
    target: date
    source: date
    format: "%Y-%m-%d"
  amount:
    target: amount
    source: amount
  type:
    target: type
    source: amount
    detection_method: sign
  description:
    target: description
    source: description
"""

CSV_ACCOUNT_MAPPING = """
  account:
    target: account
    default: Checking
"""

CSV_ACCOUNT_DEDUPLICATION = """
deduplication:
  - type: compare
    fields:
      - date
      - amount
      - account
    match_type: strict
"""

CSV_CONTENT = """date,amount,description
2026-01-05,-50.00,Groceries
2026-01-06,1000.00,Salary
"""

TAGS_YAML_CONFIG = """
settings:
  file_type: csv
  importing: tags
mapping:
  name:
    target: tag_name
    source: name
"""


class ImportRunAccountServiceTests(TestCase):
    def setUp(self):
        self.temp_root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.temp_root, ignore_errors=True)
        temp_root_override = override_settings(IMPORT_TEMP_ROOT=self.temp_root)
        temp_root_override.enable()
        self.addCleanup(temp_root_override.disable)

        self.user = get_user_model().objects.create_user(
            email="test@example.com", password="password"
        )
        write_current_user(self.user)
        self.addCleanup(delete_current_user)

        currency = Currency.objects.create(
            code="EUR", name="Euro", decimal_places=2, prefix="€ "
        )
        self.checking = Account.objects.create(
            name="Checking", currency=currency, owner=self.user
        )
        self.savings = Account.objects.create(
            name="Savings", currency=currency, owner=self.user
        )

    def _import(self, yaml_config, file_name, content, account=None):
        profile = ImportProfile.objects.create(
            name="Profile", yaml_config=yaml_config, owner=self.user
        )
        run = ImportRun.objects.create(
            profile=profile, file_name=file_name, account=account, owner=self.user
        )
        file_path = self.temp_root / file_name
        file_path.write_text(content, encoding="utf-8")

        ImportService(run).process_file(str(file_path))

        run.refresh_from_db()
        return run

    def test_run_account_overrides_the_profile_account(self):
        run = self._import(
            CSV_SETTINGS + CSV_MAPPING + CSV_ACCOUNT_MAPPING,
            "statement.csv",
            CSV_CONTENT,
            account=self.savings,
        )

        self.assertEqual(run.status, ImportRun.Status.FINISHED)
        self.assertEqual(run.successful_rows, 2)
        self.assertEqual(Transaction.objects.filter(account=self.savings).count(), 2)
        self.assertFalse(Transaction.objects.filter(account=self.checking).exists())
        self.assertIn("Importing transactions into account 'Savings'", run.logs)

    def test_profile_account_is_used_without_a_run_account(self):
        run = self._import(
            CSV_SETTINGS + CSV_MAPPING + CSV_ACCOUNT_MAPPING,
            "statement.csv",
            CSV_CONTENT,
        )

        self.assertEqual(run.successful_rows, 2)
        self.assertEqual(Transaction.objects.filter(account=self.checking).count(), 2)

    def test_run_account_imports_with_a_profile_without_account_mapping(self):
        run = self._import(
            CSV_SETTINGS + CSV_MAPPING,
            "statement.csv",
            CSV_CONTENT,
            account=self.checking,
        )

        self.assertEqual(run.successful_rows, 2)
        expense = Transaction.objects.get(description="Groceries")
        self.assertEqual(expense.account, self.checking)
        self.assertEqual(expense.type, Transaction.Type.EXPENSE)
        self.assertEqual(expense.amount, Decimal("50.00"))

    def test_deduplication_by_account_uses_the_run_account(self):
        yaml_config = CSV_SETTINGS + CSV_MAPPING + CSV_ACCOUNT_DEDUPLICATION

        self._import(yaml_config, "first.csv", CSV_CONTENT, account=self.checking)
        # Same rows, other account: not duplicates
        into_savings = self._import(
            yaml_config, "second.csv", CSV_CONTENT, account=self.savings
        )
        # Same rows, same account: duplicates
        into_savings_again = self._import(
            yaml_config, "third.csv", CSV_CONTENT, account=self.savings
        )

        self.assertEqual(into_savings.successful_rows, 2)
        self.assertEqual(into_savings.skipped_rows, 0)
        self.assertEqual(into_savings_again.successful_rows, 0)
        self.assertEqual(into_savings_again.skipped_rows, 2)
        self.assertEqual(Transaction.objects.filter(account=self.savings).count(), 2)

    def test_qif_run_account_is_used_instead_of_the_file_name(self):
        yaml_config = """
settings:
  file_type: qif
  importing: transactions
  date_format: "%d/%m/%Y"
mapping: {}
"""
        content = """!Type:Bank
D05/01/2026
T-100.00
PSupermarket
^
"""
        run = self._import(
            yaml_config, "export-2026.qif", content, account=self.savings
        )

        self.assertEqual(run.status, ImportRun.Status.FINISHED)
        transaction = Transaction.objects.get()
        self.assertEqual(transaction.account, self.savings)
        self.assertEqual(transaction.amount, Decimal("100.00"))


class ImportRunAccountTestCase(ImportObjectPermissionTestCase):
    def setUp(self):
        super().setUp()
        self.temp_root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.temp_root, ignore_errors=True)
        temp_root_override = override_settings(IMPORT_TEMP_ROOT=self.temp_root)
        temp_root_override.enable()
        self.addCleanup(temp_root_override.disable)

        currency = Currency.objects.create(
            code="EUR", name="Euro", decimal_places=2, prefix="€ "
        )
        self.account = Account.all_objects.create(
            name="Checking", currency=currency, owner=self.owner
        )
        self.archived_account = Account.all_objects.create(
            name="Old checking", currency=currency, owner=self.owner, is_archived=True
        )
        self.strangers_account = Account.all_objects.create(
            name="Stranger's checking", currency=currency, owner=self.stranger
        )
        self.tags_profile = ImportProfile.all_objects.create(
            name="Tags profile", yaml_config=TAGS_YAML_CONFIG, owner=self.owner
        )


class ImportRunAccountViewTests(ImportRunAccountTestCase):
    def _upload_form(self, profile):
        self.login(self.owner)
        response = self.client.get(
            reverse("import_run_add", kwargs={"profile_id": profile.id}), **HTMX
        )
        self.assertEqual(response.status_code, 200)
        return response.context["form"]

    def test_upload_form_offers_active_accounts_for_transaction_profiles(self):
        form = self._upload_form(self.private_profile)

        self.assertIn("account", form.fields)
        self.assertFalse(form.fields["account"].required)
        self.assertEqual(list(form.fields["account"].queryset), [self.account])

    def test_upload_form_has_no_account_for_other_profiles(self):
        form = self._upload_form(self.tags_profile)

        self.assertNotIn("account", form.fields)

    @patch("apps.import_app.views.process_import.defer")
    def test_web_upload_stores_the_account_on_the_run(self, mock_defer):
        self.login(self.owner)
        response = self.client.post(
            reverse("import_run_add", kwargs={"profile_id": self.private_profile.id}),
            {
                "file": SimpleUploadedFile("web.csv", b"date,amount\n"),
                "account": self.account.id,
            },
            **HTMX,
        )

        self.assertEqual(response.status_code, 204)
        run = ImportRun.all_objects.get(file_name="web.csv")
        self.assertEqual(run.account, self.account)
        mock_defer.assert_called_once()

    @patch("apps.import_app.views.process_import.defer")
    def test_web_upload_without_account_keeps_the_profile_account(self, mock_defer):
        self.login(self.owner)
        response = self.client.post(
            reverse("import_run_add", kwargs={"profile_id": self.private_profile.id}),
            {"file": SimpleUploadedFile("web.csv", b"date,amount\n")},
            **HTMX,
        )

        self.assertEqual(response.status_code, 204)
        self.assertIsNone(ImportRun.all_objects.get(file_name="web.csv").account)

    @patch("apps.import_app.views.process_import.defer")
    def test_web_upload_rejects_another_users_account(self, mock_defer):
        self.login(self.owner)
        response = self.client.post(
            reverse("import_run_add", kwargs={"profile_id": self.private_profile.id}),
            {
                "file": SimpleUploadedFile("web.csv", b"date,amount\n"),
                "account": self.strangers_account.id,
            },
            **HTMX,
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("account", response.context["form"].errors)
        self.assertFalse(ImportRun.all_objects.filter(file_name="web.csv").exists())
        mock_defer.assert_not_called()

    def test_runs_list_shows_the_run_account(self):
        ImportRun.all_objects.create(
            profile=self.private_profile,
            file_name="statement.csv",
            account=self.account,
            owner=self.owner,
        )
        self.login(self.owner)
        response = self.client.get(
            reverse(
                "import_profile_runs_list",
                kwargs={"profile_id": self.private_profile.id},
            ),
            **HTMX,
        )

        self.assertContains(response, "Checking")


class ImportRunAccountAPITests(ImportRunAccountTestCase):
    def setUp(self):
        super().setUp()
        self.api = APIClient()
        self.api.force_authenticate(user=self.owner)

    def _post(self, profile, **data):
        return self.api.post(
            "/api/import/import/",
            {
                "profile_id": profile.id,
                "file": SimpleUploadedFile("api.csv", b"date,amount\n"),
                **data,
            },
            format="multipart",
        )

    @patch("apps.api.views.imports.process_import.defer")
    def test_api_upload_stores_the_account_on_the_run(self, mock_defer):
        response = self._post(self.private_profile, account_id=self.account.id)

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        run = ImportRun.all_objects.get(id=response.data["import_run_id"])
        self.assertEqual(run.account, self.account)

        response = self.api.get(f"/api/import/runs/{run.id}/")
        self.assertEqual(response.data["account"], self.account.id)

    @patch("apps.api.views.imports.process_import.defer")
    def test_api_upload_without_account_keeps_the_profile_account(self, mock_defer):
        response = self._post(self.private_profile)

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        run = ImportRun.all_objects.get(id=response.data["import_run_id"])
        self.assertIsNone(run.account)

    @patch("apps.api.views.imports.process_import.defer")
    def test_api_rejects_another_users_account(self, mock_defer):
        response = self._post(
            self.private_profile, account_id=self.strangers_account.id
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("account_id", response.data)
        mock_defer.assert_not_called()

    @patch("apps.api.views.imports.process_import.defer")
    def test_api_rejects_an_archived_account(self, mock_defer):
        response = self._post(
            self.private_profile, account_id=self.archived_account.id
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("account_id", response.data)
        mock_defer.assert_not_called()

    @patch("apps.api.views.imports.process_import.defer")
    def test_api_rejects_an_account_for_profiles_not_importing_transactions(
        self, mock_defer
    ):
        response = self._post(self.tags_profile, account_id=self.account.id)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("account_id", response.data)
        mock_defer.assert_not_called()
