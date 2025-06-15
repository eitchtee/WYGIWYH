from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db import IntegrityError
import yaml
from decimal import Decimal
from datetime import date

from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.import_app.models import ImportProfile, ImportRun
from apps.import_app.forms import ImportProfileForm
from apps.import_app.services.v1 import ImportService
from apps.import_app.schemas import version_1
from apps.transactions.models import Transaction # For Transaction.Type
from unittest.mock import patch
import tempfile
import os


class ImportProfileTests(TestCase):

    def test_import_profile_valid_yaml_v1(self):
        valid_yaml_config = """
settings:
  file_type: csv
  delimiter: ','
  encoding: utf-8
  skip_lines: 0
  trigger_transaction_rules: true
  importing: transactions
mapping:
  date:
    target: date
    source: Transaction Date
    format: '%Y-%m-%d'
  amount:
    target: amount
    source: Amount
  description:
    target: description
    source: Narrative
  account:
    target: account
    source: Account Name
    type: name
  type:
    target: type
    source: Credit Debit
    detection_method: sign # Assumes positive is income, negative is expense
  is_paid:
    target: is_paid
    detection_method: always_paid
deduplication: []
        """
        profile = ImportProfile(
            name="Test Valid Profile V1",
            yaml_config=valid_yaml_config,
            version=ImportProfile.Versions.VERSION_1
        )
        try:
            profile.full_clean()
        except ValidationError as e:
            self.fail(f"Valid YAML config raised ValidationError: {e.error_dict}")

        # Optional: Save and retrieve
        profile.save()
        retrieved_profile = ImportProfile.objects.get(pk=profile.pk)
        self.assertIsNotNone(retrieved_profile)
        self.assertEqual(retrieved_profile.name, "Test Valid Profile V1")

    def test_import_profile_invalid_yaml_syntax_v1(self):
        invalid_yaml = "settings: { file_type: csv, delimiter: ','" # Malformed YAML
        profile = ImportProfile(
            name="Test Invalid Syntax V1",
            yaml_config=invalid_yaml,
            version=ImportProfile.Versions.VERSION_1
        )
        with self.assertRaises(ValidationError) as cm:
            profile.full_clean()

        self.assertIn('yaml_config', cm.exception.error_dict)
        self.assertTrue(any("YAML" in error.message.lower() or "syntax" in error.message.lower() for error in cm.exception.error_dict['yaml_config']))

    def test_import_profile_schema_validation_error_v1(self):
        schema_error_yaml = """
settings:
  file_type: csv
  importing: transactions
mapping:
  date: # Missing 'format' which is required for TransactionDateMapping
    target: date
    source: Transaction Date
        """
        profile = ImportProfile(
            name="Test Schema Error V1",
            yaml_config=schema_error_yaml,
            version=ImportProfile.Versions.VERSION_1
        )
        with self.assertRaises(ValidationError) as cm:
            profile.full_clean()

        self.assertIn('yaml_config', cm.exception.error_dict)
        # Pydantic errors usually mention the field and "field required" or similar
        self.assertTrue(any("format" in error.message.lower() and "field required" in error.message.lower()
                            for error in cm.exception.error_dict['yaml_config']),
                        f"Error messages: {[e.message for e in cm.exception.error_dict['yaml_config']]}")


    def test_import_profile_custom_validate_mappings_error_v1(self):
        custom_validate_yaml = """
settings:
  file_type: csv
  importing: transactions # Importing transactions
mapping:
  account_name: # This is an AccountNameMapping, not suitable for 'transactions' importing setting
    target: account_name
    source: AccName
        """
        profile = ImportProfile(
            name="Test Custom Validate Error V1",
            yaml_config=custom_validate_yaml,
            version=ImportProfile.Versions.VERSION_1
        )
        with self.assertRaises(ValidationError) as cm:
            profile.full_clean()

        self.assertIn('yaml_config', cm.exception.error_dict)
        # Check for the specific message raised by custom_validate_mappings
        # The message is "Mapping type AccountNameMapping not allowed for importing 'transactions'."
        self.assertTrue(any("mapping type accountnamemapping not allowed for importing 'transactions'" in error.message.lower()
                            for error in cm.exception.error_dict['yaml_config']),
                        f"Error messages: {[e.message for e in cm.exception.error_dict['yaml_config']]}")


    def test_import_profile_name_unique(self):
        valid_yaml_config = """
settings:
  file_type: csv
  importing: transactions
mapping:
  date:
    target: date
    source: Date
    format: '%Y-%m-%d'
        """ # Minimal valid YAML for this test

        ImportProfile.objects.create(
            name="Unique Name Test",
            yaml_config=valid_yaml_config,
            version=ImportProfile.Versions.VERSION_1
        )

        profile2 = ImportProfile(
            name="Unique Name Test", # Same name
            yaml_config=valid_yaml_config,
            version=ImportProfile.Versions.VERSION_1
        )

        # full_clean should catch this because of the unique constraint on the model field.
        # Django's Model.full_clean() calls Model.validate_unique().
        with self.assertRaises(ValidationError) as cm:
            profile2.full_clean()

        self.assertIn('name', cm.exception.error_dict)
        self.assertTrue(any("already exists" in error.message.lower() for error in cm.exception.error_dict['name']))

        # As a fallback, or for more direct DB constraint testing, also test IntegrityError on save if full_clean didn't catch it.
        # This will only be reached if the full_clean() above somehow passes.
        # try:
        #     profile2.save()
        # except IntegrityError:
        #     pass # Expected if full_clean didn't catch it
        # else:
        #     if 'name' not in cm.exception.error_dict: # If full_clean passed and save also passed
        #         self.fail("IntegrityError not raised for duplicate name on save(), and full_clean() didn't catch it.")

    def test_import_profile_form_valid_data(self):
        valid_yaml_config = """
settings:
  file_type: csv
  delimiter: ','
  encoding: utf-8
  skip_lines: 0
  trigger_transaction_rules: true
  importing: transactions
mapping:
  date:
    target: date
    source: Transaction Date
    format: '%Y-%m-%d'
  amount:
    target: amount
    source: Amount
  description:
    target: description
    source: Narrative
  account:
    target: account
    source: Account Name
    type: name
  type:
    target: type
    source: Credit Debit
    detection_method: sign
  is_paid:
    target: is_paid
    detection_method: always_paid
deduplication: []
        """
        form_data = {
            'name': 'Form Test Valid',
            'yaml_config': valid_yaml_config,
            'version': ImportProfile.Versions.VERSION_1
        }
        form = ImportProfileForm(data=form_data)
        self.assertTrue(form.is_valid(), f"Form errors: {form.errors.as_json()}")

        profile = form.save()
        self.assertIsNotNone(profile.pk)
        self.assertEqual(profile.name, 'Form Test Valid')
        # YAMLField might re-serialize the YAML, so direct string comparison might be brittle
        # if spacing/ordering changes. However, for now, let's assume it's stored as provided or close enough.
        # A more robust check would be to load both YAMLs and compare the resulting dicts.
        self.assertEqual(profile.yaml_config.strip(), valid_yaml_config.strip())
        self.assertEqual(profile.version, ImportProfile.Versions.VERSION_1)

    def test_import_profile_form_invalid_yaml(self):
        # Using a YAML that causes a schema validation error (missing 'format' for date mapping)
        invalid_yaml_for_form = """
settings:
  file_type: csv
  importing: transactions
mapping:
  date:
    target: date
    source: Transaction Date
        """
        form_data = {
            'name': 'Form Test Invalid',
            'yaml_config': invalid_yaml_for_form,
            'version': ImportProfile.Versions.VERSION_1
        }
        form = ImportProfileForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn('yaml_config', form.errors)
        # Check for a message indicating schema validation failure
        self.assertTrue(any("field required" in error.lower() for error in form.errors['yaml_config']))


class ImportServiceTests(TestCase):
    # ... (existing setUp and other test methods from previous task) ...
    def setUp(self):
        minimal_yaml_config = """
settings:
  file_type: csv
  importing: transactions
mapping:
  description:
    target: description
    source: Desc
        """
        self.profile = ImportProfile.objects.create(
            name="Test Service Profile",
            yaml_config=minimal_yaml_config,
            version=ImportProfile.Versions.VERSION_1
        )
        self.import_run = ImportRun.objects.create(
            profile=self.profile,
            status=ImportRun.Status.PENDING
        )
        # self.service is initialized in each test to allow specific mapping_config
        # or to re-initialize if service state changes (though it shouldn't for these private methods)

    # Tests for _transform_value
    def test_transform_value_replace(self):
        service = ImportService(self.import_run)
        mapping_config = version_1.ColumnMapping(target="description", source="Desc") # Basic mapping
        mapping_config.transformations = [
            version_1.ReplaceTransformationRule(type="replace", pattern="old", replacement="new")
        ]
        transformed_value = service._transform_value("this is old text", mapping_config)
        self.assertEqual(transformed_value, "this is new text")

    def test_transform_value_date_format(self):
        service = ImportService(self.import_run)
        # DateFormatTransformationRule is typically part of a DateMapping, but testing transform directly
        mapping_config = version_1.TransactionDateMapping(target="date", source="Date", format="%d/%m/%Y") # format is for final coercion
        mapping_config.transformations = [
            version_1.DateFormatTransformationRule(type="date_format", original_format="%Y-%m-%d", new_format="%d/%m/%Y")
        ]
        transformed_value = service._transform_value("2023-01-15", mapping_config)
        self.assertEqual(transformed_value, "15/01/2023")

    def test_transform_value_regex_replace(self):
        service = ImportService(self.import_run)
        mapping_config = version_1.ColumnMapping(target="description", source="Desc")
        mapping_config.transformations = [
            version_1.ReplaceTransformationRule(type="regex", pattern=r"\\d+", replacement="NUM")
        ]
        transformed_value = service._transform_value("abc123xyz456", mapping_config)
        self.assertEqual(transformed_value, "abcNUMxyzNUM")

    # Tests for _coerce_type
    def test_coerce_type_string_to_decimal(self):
        service = ImportService(self.import_run)
        # TransactionAmountMapping has coerce_to="positive_decimal" by default
        mapping_config = version_1.TransactionAmountMapping(target="amount", source="Amt")

        coerced = service._coerce_type("123.45", mapping_config)
        self.assertEqual(coerced, Decimal("123.45"))

        coerced_neg = service._coerce_type("-123.45", mapping_config)
        self.assertEqual(coerced_neg, Decimal("123.45")) # positive_decimal behavior

        # Test with coerce_to="decimal"
        mapping_config_decimal = version_1.TransactionAmountMapping(target="amount", source="Amt", coerce_to="decimal")
        coerced_neg_decimal = service._coerce_type("-123.45", mapping_config_decimal)
        self.assertEqual(coerced_neg_decimal, Decimal("-123.45"))


    def test_coerce_type_string_to_date(self):
        service = ImportService(self.import_run)
        mapping_config = version_1.TransactionDateMapping(target="date", source="Dt", format="%Y-%m-%d")
        coerced = service._coerce_type("2023-01-15", mapping_config)
        self.assertEqual(coerced, date(2023, 1, 15))

    def test_coerce_type_string_to_transaction_type_sign(self):
        service = ImportService(self.import_run)
        mapping_config = version_1.TransactionTypeMapping(target="type", source="TType", detection_method="sign")

        self.assertEqual(service._coerce_type("100.00", mapping_config), Transaction.Type.INCOME)
        self.assertEqual(service._coerce_type("-100.00", mapping_config), Transaction.Type.EXPENSE)
        self.assertEqual(service._coerce_type("0.00", mapping_config), Transaction.Type.EXPENSE) # Sign detection treats 0 as expense
        self.assertEqual(service._coerce_type("+200", mapping_config), Transaction.Type.INCOME)

    def test_coerce_type_string_to_transaction_type_keywords(self):
        service = ImportService(self.import_run)
        mapping_config = version_1.TransactionTypeMapping(
            target="type",
            source="TType",
            detection_method="keywords",
            income_keywords=["credit", "dep"],
            expense_keywords=["debit", "wdrl"]
        )
        self.assertEqual(service._coerce_type("Monthly Credit", mapping_config), Transaction.Type.INCOME)
        self.assertEqual(service._coerce_type("ATM WDRL", mapping_config), Transaction.Type.EXPENSE)
        self.assertIsNone(service._coerce_type("Unknown Type", mapping_config)) # No keyword match

    @patch('apps.import_app.services.v1.os.remove')
    def test_process_file_simple_csv_transactions(self, mock_os_remove):
        simple_transactions_yaml = """
settings:
  file_type: csv
  importing: transactions
  delimiter: ','
  skip_lines: 0
mapping:
  date: {target: date, source: Date, format: '%Y-%m-%d'}
  amount: {target: amount, source: Amount}
  description: {target: description, source: Description}
  type: {target: type, source: Type, detection_method: always_income}
  account: {target: account, source: AccountName, type: name}
"""
        self.profile.yaml_config = simple_transactions_yaml
        self.profile.save()
        self.import_run.refresh_from_db() # Ensure import_run has the latest profile reference if needed

        csv_content = "Date,Amount,Description,Type,AccountName\n2023-01-01,100.00,Test Deposit,INCOME,TestAcc"

        temp_file_path = None
        try:
            # Ensure TEMP_DIR exists if ImportService relies on it being pre-existing
            # For NamedTemporaryFile, dir just needs to be a valid directory path.
            # If ImportService.TEMP_DIR is a class variable pointing to a specific path,
            # it should be created or mocked if it doesn't exist by default.
            # For simplicity, let's assume it exists or tempfile handles it gracefully.
            # If ImportService.TEMP_DIR is not guaranteed, use default temp dir.
            temp_dir = getattr(ImportService, 'TEMP_DIR', None)
            if temp_dir and not os.path.exists(temp_dir):
                os.makedirs(temp_dir, exist_ok=True)

            with tempfile.NamedTemporaryFile(mode='w+', delete=False, dir=temp_dir, suffix='.csv', encoding='utf-8') as tmp_file:
                tmp_file.write(csv_content)
                temp_file_path = tmp_file.name

            self.addCleanup(lambda: os.remove(temp_file_path) if temp_file_path and os.path.exists(temp_file_path) else None)

            service = ImportService(self.import_run)

            with patch.object(service, '_create_transaction') as mock_create_transaction:
                service.process_file(temp_file_path)

                self.import_run.refresh_from_db() # Refresh to get updated status and counts
                self.assertEqual(self.import_run.status, ImportRun.Status.FINISHED)
                self.assertEqual(self.import_run.total_rows, 1)
                self.assertEqual(self.import_run.successful_rows, 1)

                mock_create_transaction.assert_called_once()

                # The first argument to _create_transaction is the row_data dictionary
                args_dict = mock_create_transaction.call_args[0][0]

                self.assertEqual(args_dict['date'], date(2023, 1, 1))
                self.assertEqual(args_dict['amount'], Decimal('100.00'))
                self.assertEqual(args_dict['description'], "Test Deposit")
                self.assertEqual(args_dict['type'], Transaction.Type.INCOME)

                # Account 'TestAcc' does not exist, so _map_row should resolve 'account' to None.
                # This assumes the default behavior of AccountMapping(type='name') when an account is not found
                # and creation of new accounts from mapping is not enabled/implemented in _map_row for this test.
                self.assertIsNone(args_dict.get('account'),
                                  "Account should be None as 'TestAcc' is not created in this test setup.")

            mock_os_remove.assert_called_once_with(temp_file_path)

        finally:
            # This cleanup is now handled by self.addCleanup, but kept for safety if addCleanup fails early.
            if temp_file_path and os.path.exists(temp_file_path) and not mock_os_remove.called:
                 # If mock_os_remove was not called (e.g., an error before service.process_file finished),
                 # we might need to manually clean up if addCleanup didn't register or run.
                 # However, addCleanup is generally robust.
                 pass
