"""Tests for the `line` transformation, which reads a line outside the table, like a header cell."""

import shutil
import tempfile
from pathlib import Path

import openpyxl
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.accounts.models import Account
from apps.common.middleware.thread_local import delete_current_user, write_current_user
from apps.currencies.models import Currency
from apps.import_app.models import ImportProfile, ImportRun
from apps.import_app.services.v1 import ImportService
from apps.transactions.models import Transaction

MAPPING = """
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
  account:
    target: account
    transformations:
{account_transformations}
"""

# The account name sits in the header, above the table
CSV_CONTENT = """Bank statement
Account:;Savings
Account number:;Savings 1234

date;amount;description
2026-01-05;-50.00;Groceries
2026-01-06;1000.00;Salary
"""


class LineTransformationTests(TestCase):
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
        Account.objects.create(name="Checking", currency=currency, owner=self.user)
        self.savings = Account.objects.create(
            name="Savings", currency=currency, owner=self.user
        )

    def _import(self, settings, account_transformations, file_name, write):
        yaml_config = settings + MAPPING.format(
            account_transformations=account_transformations
        )
        profile = ImportProfile.objects.create(
            name="Profile", yaml_config=yaml_config, owner=self.user
        )
        run = ImportRun.objects.create(
            profile=profile, file_name=file_name, owner=self.user
        )
        file_path = self.temp_root / file_name
        write(file_path)

        ImportService(run).process_file(str(file_path))

        run.refresh_from_db()
        return run

    def _import_csv(self, account_transformations):
        settings = """
settings:
  file_type: csv
  importing: transactions
  delimiter: ";"
  skip_lines: 4
  trigger_transaction_rules: false
"""
        return self._import(
            settings,
            account_transformations,
            "statement.csv",
            lambda path: path.write_text(CSV_CONTENT, encoding="utf-8"),
        )

    def assert_imported_into_savings(self, run):
        self.assertEqual(run.status, ImportRun.Status.FINISHED, run.logs)
        self.assertEqual(run.successful_rows, 2)
        self.assertEqual(Transaction.objects.filter(account=self.savings).count(), 2)

    def test_csv_reads_a_cell_from_a_skipped_line(self):
        run = self._import_csv(
            """
      - type: line
        line: 2
        column: 2
"""
        )

        self.assert_imported_into_savings(run)

    def test_csv_whole_line_cleaned_with_regex(self):
        run = self._import_csv(
            """
      - type: line
        line: 3
      - type: regex
        pattern: '^Account number:;(\\w+) \\d+$'
        replacement: '\\1'
"""
        )

        self.assert_imported_into_savings(run)

    def test_xlsx_reads_a_cell_above_the_header(self):
        def write(path):
            workbook = openpyxl.Workbook()
            sheet = workbook.active
            sheet["A1"] = "Bank statement"
            sheet["A4"] = "Account:"
            sheet["B4"] = "Savings"
            sheet.append([])
            sheet.append(["date", "amount", "description"])
            sheet.append(["2026-01-05", "-50.00", "Groceries"])
            sheet.append(["2026-01-06", "1000.00", "Salary"])
            workbook.save(path)

        settings = """
settings:
  file_type: xlsx
  importing: transactions
  start_row: 6
  trigger_transaction_rules: false
"""
        run = self._import(
            settings,
            """
      - type: line
        line: 4
        column: 2
""",
            "statement.xlsx",
            write,
        )

        self.assert_imported_into_savings(run)
