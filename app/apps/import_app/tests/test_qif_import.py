from decimal import Decimal
import os
import shutil
from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.accounts.models import Account, AccountGroup
from apps.currencies.models import Currency
from apps.common.middleware.thread_local import write_current_user, delete_current_user
from apps.import_app.models import ImportProfile, ImportRun
from apps.import_app.services.v1 import ImportService
from apps.transactions.models import (
    Transaction,
)


class QIFImportTests(TestCase):
    def setUp(self):
        # Patch TEMP_DIR for testing
        self.original_temp_dir = ImportService.TEMP_DIR
        self.test_dir = os.path.abspath("temp_test_import")
        ImportService.TEMP_DIR = self.test_dir
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
        ImportService.TEMP_DIR = self.original_temp_dir
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

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
