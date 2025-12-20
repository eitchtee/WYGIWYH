"""
Tests for ImportService v1, specifically for deduplication logic.

These tests verify that the _check_duplicate_transaction method handles
different field types correctly, particularly ensuring that __iexact
is only used for string fields (not dates, decimals, etc.).
"""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.accounts.models import Account, AccountGroup
from apps.currencies.models import Currency
from apps.import_app.models import ImportProfile, ImportRun
from apps.import_app.services.v1 import ImportService
from apps.transactions.models import Transaction


class DeduplicationTests(TestCase):
    """Tests for transaction deduplication during import."""

    def setUp(self):
        """Set up test data."""
        self.currency = Currency.objects.create(
            code="USD", name="US Dollar", decimal_places=2, prefix="$ "
        )
        self.account_group = AccountGroup.objects.create(name="Test Group")
        self.account = Account.objects.create(
            name="Test Account", group=self.account_group, currency=self.currency
        )

        # Create an existing transaction for deduplication tests
        self.existing_transaction = Transaction.objects.create(
            account=self.account,
            type=Transaction.Type.EXPENSE,
            date=date(2024, 1, 15),
            amount=Decimal("100.00"),
            description="Existing Transaction",
            internal_id="ABC123",
        )

    def _create_import_service_with_deduplication(
        self, fields: list[str], match_type: str = "lax"
    ) -> ImportService:
        """Helper to create an ImportService with specific deduplication rules."""
        yaml_config = f"""
settings:
  file_type: csv
  importing: transactions
  trigger_transaction_rules: false
mapping:
  date_field:
    source: date
    target: date
    format: "%Y-%m-%d"
  amount_field:
    source: amount
    target: amount
  description_field:
    source: description
    target: description
  account_field:
    source: account
    target: account
    type: id
deduplication:
  - type: compare
    fields: {fields}
    match_type: {match_type}
"""
        profile = ImportProfile.objects.create(
            name=f"Test Profile {match_type} {'_'.join(fields)}",
            yaml_config=yaml_config,
            version=ImportProfile.Versions.VERSION_1,
        )
        import_run = ImportRun.objects.create(
            profile=profile,
            file_name="test.csv",
        )
        return ImportService(import_run)

    def test_deduplication_with_date_field_strict_match(self):
        """Test that date fields work with strict matching."""
        service = self._create_import_service_with_deduplication(
            fields=["date"], match_type="strict"
        )

        # Should find duplicate when date matches
        is_duplicate = service._check_duplicate_transaction({"date": date(2024, 1, 15)})
        self.assertTrue(is_duplicate)

        # Should not find duplicate when date differs
        is_duplicate = service._check_duplicate_transaction({"date": date(2024, 2, 20)})
        self.assertFalse(is_duplicate)

    def test_deduplication_with_date_field_lax_match(self):
        """
        Test that date fields use strict matching even when match_type is 'lax'.

        This is the fix for the UPPER(date) PostgreSQL error. Date fields
        cannot use __iexact, so they should fall back to strict matching.
        """
        service = self._create_import_service_with_deduplication(
            fields=["date"], match_type="lax"
        )

        # Should find duplicate when date matches (using strict comparison)
        is_duplicate = service._check_duplicate_transaction({"date": date(2024, 1, 15)})
        self.assertTrue(is_duplicate)

        # Should not find duplicate when date differs
        is_duplicate = service._check_duplicate_transaction({"date": date(2024, 2, 20)})
        self.assertFalse(is_duplicate)

    def test_deduplication_with_amount_field_lax_match(self):
        """
        Test that Decimal fields use strict matching even when match_type is 'lax'.

        Decimal fields cannot use __iexact, so they should fall back to strict matching.
        """
        service = self._create_import_service_with_deduplication(
            fields=["amount"], match_type="lax"
        )

        # Should find duplicate when amount matches
        is_duplicate = service._check_duplicate_transaction(
            {"amount": Decimal("100.00")}
        )
        self.assertTrue(is_duplicate)

        # Should not find duplicate when amount differs
        is_duplicate = service._check_duplicate_transaction(
            {"amount": Decimal("200.00")}
        )
        self.assertFalse(is_duplicate)

    def test_deduplication_with_string_field_lax_match(self):
        """
        Test that string fields use case-insensitive matching with match_type 'lax'.
        """
        service = self._create_import_service_with_deduplication(
            fields=["description"], match_type="lax"
        )

        # Should find duplicate with case-insensitive match
        is_duplicate = service._check_duplicate_transaction(
            {"description": "EXISTING TRANSACTION"}
        )
        self.assertTrue(is_duplicate)

        # Should find duplicate with exact case match
        is_duplicate = service._check_duplicate_transaction(
            {"description": "Existing Transaction"}
        )
        self.assertTrue(is_duplicate)

        # Should not find duplicate when description differs
        is_duplicate = service._check_duplicate_transaction(
            {"description": "Different Transaction"}
        )
        self.assertFalse(is_duplicate)

    def test_deduplication_with_string_field_strict_match(self):
        """
        Test that string fields use case-sensitive matching with match_type 'strict'.
        """
        service = self._create_import_service_with_deduplication(
            fields=["description"], match_type="strict"
        )

        # Should NOT find duplicate with different case (strict matching)
        is_duplicate = service._check_duplicate_transaction(
            {"description": "EXISTING TRANSACTION"}
        )
        self.assertFalse(is_duplicate)

        # Should find duplicate with exact case match
        is_duplicate = service._check_duplicate_transaction(
            {"description": "Existing Transaction"}
        )
        self.assertTrue(is_duplicate)

    def test_deduplication_with_multiple_fields_mixed_types(self):
        """
        Test deduplication with multiple fields of different types.

        Verifies that string fields use __iexact while non-string fields
        use strict matching, all in the same deduplication rule.
        """
        service = self._create_import_service_with_deduplication(
            fields=["date", "amount", "description"], match_type="lax"
        )

        # Should find duplicate when all fields match (with case-insensitive description)
        is_duplicate = service._check_duplicate_transaction(
            {
                "date": date(2024, 1, 15),
                "amount": Decimal("100.00"),
                "description": "existing transaction",  # lowercase should match
            }
        )
        self.assertTrue(is_duplicate)

        # Should NOT find duplicate when date differs
        is_duplicate = service._check_duplicate_transaction(
            {
                "date": date(2024, 2, 20),
                "amount": Decimal("100.00"),
                "description": "existing transaction",
            }
        )
        self.assertFalse(is_duplicate)

        # Should NOT find duplicate when amount differs
        is_duplicate = service._check_duplicate_transaction(
            {
                "date": date(2024, 1, 15),
                "amount": Decimal("999.99"),
                "description": "existing transaction",
            }
        )
        self.assertFalse(is_duplicate)

    def test_deduplication_with_internal_id_lax_match(self):
        """Test deduplication with internal_id field using lax matching."""
        service = self._create_import_service_with_deduplication(
            fields=["internal_id"], match_type="lax"
        )

        # Should find duplicate with case-insensitive match
        is_duplicate = service._check_duplicate_transaction(
            {"internal_id": "abc123"}  # lowercase should match ABC123
        )
        self.assertTrue(is_duplicate)

        # Should find duplicate with exact match
        is_duplicate = service._check_duplicate_transaction({"internal_id": "ABC123"})
        self.assertTrue(is_duplicate)

        # Should not find duplicate when internal_id differs
        is_duplicate = service._check_duplicate_transaction({"internal_id": "XYZ789"})
        self.assertFalse(is_duplicate)

    def test_no_duplicate_when_no_transactions_exist(self):
        """Test that no duplicate is found when there are no matching transactions."""
        # Hard delete to bypass signals that require user context
        self.existing_transaction.hard_delete()

        service = self._create_import_service_with_deduplication(
            fields=["date", "amount"], match_type="lax"
        )

        is_duplicate = service._check_duplicate_transaction(
            {
                "date": date(2024, 1, 15),
                "amount": Decimal("100.00"),
            }
        )
        self.assertFalse(is_duplicate)

    def test_deduplication_with_missing_field_in_data(self):
        """Test that missing fields in transaction_data are handled gracefully."""
        service = self._create_import_service_with_deduplication(
            fields=["date", "nonexistent_field"], match_type="lax"
        )

        # Should still work, only checking the fields that exist
        is_duplicate = service._check_duplicate_transaction(
            {
                "date": date(2024, 1, 15),
            }
        )
        self.assertTrue(is_duplicate)
