from datetime import date
from decimal import Decimal
import hashlib
import os
import shutil
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from apps.accounts.models import Account, AccountGroup
from apps.currencies.models import Currency
from apps.common.middleware.thread_local import write_current_user, delete_current_user
from apps.import_app.models import ImportProfile, ImportRun
from apps.import_app.services.v1 import ImportService
from apps.transactions.models import (
    Transaction,
)

QIF_YAML_CONFIG = """
settings:
  file_type: qif
  importing: transactions
  date_format: "%d/%m/%Y"
mapping: {}
"""

# A salary, then two purchases with the same date, amount and payee
IDENTICAL_TRANSACTIONS_CONTENT = """!Type:Bank
D04/01/2015
T100.00
PSalary
^
D05/01/2015
T-4.50
PCoffee Shop
^
D05/01/2015
T-4.50
PCoffee Shop
^
"""


class QIFImportTests(TestCase):
    def setUp(self):
        # Point the import temp folder somewhere disposable for testing
        self.test_dir = os.path.abspath("temp_test_import")
        temp_root_override = override_settings(IMPORT_TEMP_ROOT=self.test_dir)
        temp_root_override.enable()
        self.addCleanup(temp_root_override.disable)
        os.makedirs(self.test_dir, exist_ok=True)

        # Create user and set context
        User = get_user_model()
        self.user = User.objects.create_user(
            email="test@example.com", password="password"
        )
        write_current_user(self.user)

        self.currency = Currency.objects.create(
            code="BRL", name="Real", decimal_places=2, prefix="R$ "
        )
        self.group = AccountGroup.objects.create(name="Test Group", owner=self.user)
        self.account = Account.objects.create(
            name="bradesco-checking",
            group=self.group,
            currency=self.currency,
            owner=self.user,
        )

    def tearDown(self):
        delete_current_user()
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def _import_qif(self, content, account=None, filename="bradesco-checking.qif"):
        file_path = os.path.join(self.test_dir, filename)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        profile = ImportProfile.objects.create(
            name="QIF Profile",
            yaml_config=QIF_YAML_CONFIG,
            version=ImportProfile.Versions.VERSION_1,
        )
        run = ImportRun.objects.create(
            profile=profile, file_name=filename, account=account
        )
        ImportService(run).process_file(file_path)
        run.refresh_from_db()
        return run

    def test_import_single_qif_valid_mapping(self):
        content = """!Type:Bank
D04/01/2015
T8069.46
PMy Payee -> Entity
MNote -> Desc
LOld Cat:New Tag
^
D05/01/2015
T-100.00
PSupermarket
MWeekly shopping
L[Transfer]
^
"""
        filename = "bradesco-checking.qif"
        file_path = os.path.join(self.test_dir, filename)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        yaml_config = """
settings:
  file_type: qif
  importing: transactions
  date_format: "%d/%m/%Y"
mapping: {}
"""
        profile = ImportProfile.objects.create(
            name="QIF Profile",
            yaml_config=yaml_config,
            version=ImportProfile.Versions.VERSION_1,
        )
        run = ImportRun.objects.create(profile=profile, file_name=filename)
        service = ImportService(run)

        service.process_file(file_path)

        self.assertEqual(Transaction.objects.count(), 2)

        # Transaction 1: Income, Category+Tag
        t1 = Transaction.objects.get(description="Note -> Desc")
        self.assertEqual(t1.amount, Decimal("8069.46"))
        self.assertEqual(t1.type, Transaction.Type.INCOME)
        self.assertEqual(t1.category.name, "Old Cat")
        self.assertTrue(t1.tags.filter(name="New Tag").exists())
        self.assertTrue(t1.entities.filter(name="My Payee -> Entity").exists())
        self.assertEqual(t1.account, self.account)

        # Transaction 2: Expense, Transfer ([Transfer] -> Description)
        t2 = Transaction.objects.get(description="Transfer")
        self.assertEqual(t2.amount, Decimal("100.00"))
        self.assertEqual(t2.type, Transaction.Type.EXPENSE)
        self.assertIsNone(t2.category)
        self.assertFalse(t2.tags.exists())
        self.assertTrue(t2.entities.filter(name="Supermarket").exists())
        self.assertEqual(t2.description, "Transfer")

    def test_import_deduplication_hash(self):
        # Same content twice. Should result in only 1 transaction due to hash deduplication.
        content = """!Type:Bank
D04/01/2015
T100.00
POK
^
"""
        filename = "bradesco-checking.qif"
        file_path = os.path.join(self.test_dir, filename)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        yaml_config = """
settings:
  file_type: qif
  importing: transactions
  date_format: "%d/%m/%Y"
mapping: {}
"""
        profile = ImportProfile.objects.create(
            name="QIF Profile",
            yaml_config=yaml_config,
            version=ImportProfile.Versions.VERSION_1,
        )
        run = ImportRun.objects.create(profile=profile, file_name=filename)
        service = ImportService(run)

        # First run
        service.process_file(file_path)
        self.assertEqual(Transaction.objects.count(), 1)

        # Service deletes file after processing, so recreate it for second run
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        # Second run - Duplicate content
        service.process_file(file_path)
        self.assertEqual(Transaction.objects.count(), 1)

    def test_import_strict_error_rollback(self):
        # atomic check.
        # Transaction 1 valid, Transaction 2 invalid date.
        content = """!Type:Bank
D04/01/2015
T100.00
POK
^
DINVALID
T100.00
PBad
^
"""
        filename = "bradesco-checking.qif"
        file_path = os.path.join(self.test_dir, filename)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        yaml_config = """
settings:
  file_type: qif
  importing: transactions
  date_format: "%d/%m/%Y"
  skip_errors: false
mapping: {}
"""
        profile = ImportProfile.objects.create(
            name="QIF Profile",
            yaml_config=yaml_config,
            version=ImportProfile.Versions.VERSION_1,
        )
        run = ImportRun.objects.create(profile=profile, file_name=filename)
        service = ImportService(run)

        with self.assertRaises(Exception) as cm:
            service.process_file(file_path)
        self.assertEqual(str(cm.exception), "Import failed")

        # Should be 0 transactions because of atomic rollback
        self.assertEqual(Transaction.objects.count(), 0)

    def test_import_missing_account(self):
        # File with account name that doesn't exist
        content = """!Type:Bank
D04/01/2015
T100.00
POK
^
"""
        filename = "missing-account.qif"
        file_path = os.path.join(self.test_dir, filename)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        yaml_config = """
settings:
  file_type: qif
  importing: transactions
  date_format: "%d/%m/%Y"
mapping: {}
"""
        profile = ImportProfile.objects.create(
            name="QIF Profile",
            yaml_config=yaml_config,
            version=ImportProfile.Versions.VERSION_1,
        )
        run = ImportRun.objects.create(profile=profile, file_name=filename)
        service = ImportService(run)

        # Should fail because account doesn't exist
        with self.assertRaises(Exception) as cm:
            service.process_file(file_path)
        self.assertEqual(str(cm.exception), "Import failed")

    def test_import_skip_errors(self):
        # skip_errors: true.
        # Transaction 1 valid, Transaction 2 invalid date.
        content = """!Type:Bank
D04/01/2015
T100.00
POK
^
DINVALID
T100.00
PBad
^
"""
        filename = "bradesco-checking.qif"
        file_path = os.path.join(self.test_dir, filename)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        yaml_config = """
settings:
  file_type: qif
  importing: transactions
  date_format: "%d/%m/%Y"
  skip_errors: true
mapping: {}
"""
        profile = ImportProfile.objects.create(
            name="QIF Profile",
            yaml_config=yaml_config,
            version=ImportProfile.Versions.VERSION_1,
        )
        run = ImportRun.objects.create(profile=profile, file_name=filename)
        service = ImportService(run)

        service.process_file(file_path)

        # Should be 1 transaction (valid one)
        self.assertEqual(Transaction.objects.count(), 1)
        self.assertEqual(
            Transaction.objects.first().description, ""
        )  # empty desc if no memo

    def test_import_same_file_into_two_accounts(self):
        savings = Account.objects.create(
            name="bradesco-savings",
            group=self.group,
            currency=self.currency,
            owner=self.user,
        )

        into_checking = self._import_qif(
            IDENTICAL_TRANSACTIONS_CONTENT, account=self.account
        )
        into_savings = self._import_qif(IDENTICAL_TRANSACTIONS_CONTENT, account=savings)
        into_savings_again = self._import_qif(
            IDENTICAL_TRANSACTIONS_CONTENT, account=savings
        )

        self.assertEqual(into_checking.successful_rows, 3)
        self.assertEqual(into_savings.successful_rows, 3)
        self.assertEqual(into_savings.skipped_rows, 0)
        self.assertEqual(into_savings_again.successful_rows, 0)
        self.assertEqual(into_savings_again.skipped_rows, 3)
        self.assertEqual(Transaction.objects.filter(account=self.account).count(), 3)
        self.assertEqual(Transaction.objects.filter(account=savings).count(), 3)

    def test_import_identical_transactions_in_one_file(self):
        first_run = self._import_qif(IDENTICAL_TRANSACTIONS_CONTENT)

        self.assertEqual(first_run.successful_rows, 3)
        self.assertEqual(first_run.skipped_rows, 0)
        coffees = Transaction.objects.filter(entities__name="Coffee Shop")
        self.assertEqual(coffees.count(), 2)
        self.assertEqual(coffees.values("internal_id").distinct().count(), 2)

        # Re-importing the file still recognizes both of them
        second_run = self._import_qif(IDENTICAL_TRANSACTIONS_CONTENT)

        self.assertEqual(second_run.successful_rows, 0)
        self.assertEqual(second_run.skipped_rows, 3)
        self.assertEqual(Transaction.objects.count(), 3)

    def test_import_skips_transactions_imported_with_the_previous_hash(self):
        # Imports made before the account was part of the hash used the raw
        # lines alone, and skipped every repeat of identical transactions
        legacy_internal_id = hashlib.sha256(
            "D05/01/2015T-4.50PCoffee Shop^".encode("utf-8")
        ).hexdigest()
        Transaction.objects.create(
            account=self.account,
            type=Transaction.Type.EXPENSE,
            date=date(2015, 1, 5),
            amount=Decimal("4.50"),
            internal_id=legacy_internal_id,
        )
        savings = Account.objects.create(
            name="bradesco-savings",
            group=self.group,
            currency=self.currency,
            owner=self.user,
        )

        into_checking = self._import_qif(IDENTICAL_TRANSACTIONS_CONTENT)
        into_savings = self._import_qif(IDENTICAL_TRANSACTIONS_CONTENT, account=savings)

        # The first coffee is the one imported before, the second one was
        # skipped back then and is imported now
        self.assertEqual(into_checking.successful_rows, 2)
        self.assertEqual(into_checking.skipped_rows, 1)
        self.assertEqual(Transaction.objects.filter(account=self.account).count(), 3)
        # The previous hash doesn't say which account it was for, so it only
        # counts as a duplicate in the account the transaction is in
        self.assertEqual(into_savings.successful_rows, 3)
        self.assertEqual(into_savings.skipped_rows, 0)
        self.assertEqual(Transaction.objects.filter(account=savings).count(), 3)

    @override_settings(ENABLE_SOFT_DELETE=True)
    def test_import_skips_soft_deleted_transactions(self):
        content = """!Type:Bank
D04/01/2015
T100.00
POK
^
"""
        self._import_qif(content)
        Transaction.objects.get().delete()
        self.assertTrue(Transaction.deleted_objects.exists())

        run = self._import_qif(content)

        self.assertEqual(run.status, ImportRun.Status.FINISHED)
        self.assertEqual(run.successful_rows, 0)
        self.assertEqual(run.skipped_rows, 1)
        self.assertFalse(Transaction.objects.exists())
