import csv
import hashlib
import re
from datetime import datetime
from typing import Dict, Any, Literal

import yaml

from django.db import transaction
from django.core.files.storage import default_storage
from django.utils import timezone

from apps.import_app.models import ImportRun, ImportProfile
from apps.import_app.schemas import (
    SchemaV1,
    ColumnMappingV1,
    SettingsV1,
    HashTransformationRuleV1,
    CompareDeduplicationRuleV1,
)
from apps.transactions.models import Transaction


class ImportService:
    def __init__(self, import_run: ImportRun):
        self.import_run: ImportRun = import_run
        self.profile: ImportProfile = import_run.profile
        self.config: SchemaV1 = self._load_config()
        self.settings: SettingsV1 = self.config.settings
        self.deduplication: list[CompareDeduplicationRuleV1] = self.config.deduplication
        self.mapping: Dict[str, ColumnMappingV1] = self.config.column_mapping

    def _load_config(self) -> SchemaV1:
        yaml_data = yaml.safe_load(self.profile.yaml_config)

        if self.profile.version == ImportProfile.Versions.VERSION_1:
            return SchemaV1(**yaml_data)

        raise ValueError(f"Unsupported version: {self.profile.version}")

    def _log(self, level: str, message: str, **kwargs) -> None:
        """Add a log entry to the import run logs"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Format additional context if present
        context = ""
        if kwargs:
            context = " - " + ", ".join(f"{k}={v}" for k, v in kwargs.items())

        log_line = f"[{timestamp}] {level.upper()}: {message}{context}\n"

        # Append to existing logs
        self.import_run.logs += log_line
        self.import_run.save(update_fields=["logs"])

    def _update_status(
        self, new_status: Literal["PROCESSING", "FAILED", "FINISHED"]
    ) -> None:
        if new_status == "PROCESSING":
            self.import_run.status = ImportRun.Status.PROCESSING
        elif new_status == "FAILED":
            self.import_run.status = ImportRun.Status.FAILED
        elif new_status == "FINISHED":
            self.import_run.status = ImportRun.Status.FINISHED

        self.import_run.save(update_fields=["status"])

    @staticmethod
    def _transform_value(
        value: str, mapping: ColumnMappingV1, row: Dict[str, str] = None
    ) -> Any:
        transformed = value

        for transform in mapping.transformations:
            if transform.type == "hash":
                if not isinstance(transform, HashTransformationRuleV1):
                    continue

                # Collect all values to be hashed
                values_to_hash = []
                for field in transform.fields:
                    if field in row:
                        values_to_hash.append(str(row[field]))

                # Create hash from concatenated values
                if values_to_hash:
                    concatenated = "|".join(values_to_hash)
                    transformed = hashlib.sha256(concatenated.encode()).hexdigest()

            elif transform.type == "replace":
                transformed = transformed.replace(
                    transform.pattern, transform.replacement
                )
            elif transform.type == "regex":
                transformed = re.sub(
                    transform.pattern, transform.replacement, transformed
                )
            elif transform.type == "date_format":
                transformed = datetime.strptime(
                    transformed, transform.pattern
                ).strftime(transform.replacement)

        return transformed

    def _map_row_to_transaction(self, row: Dict[str, str]) -> Dict[str, Any]:
        transaction_data = {}

        for field, mapping in self.mapping.items():
            # If source is None, use None as the initial value
            value = row.get(mapping.source) if mapping.source else None

            # Use default_value if value is None
            if value is None:
                value = mapping.default_value

            if mapping.required and value is None and not mapping.transformations:
                raise ValueError(f"Required field {field} is missing")

            # Apply transformations even if initial value is None
            if mapping.transformations:
                value = self._transform_value(value, mapping, row)

            if value is not None:
                transaction_data[field] = value

        return transaction_data

    def _check_duplicate_transaction(self, transaction_data: Dict[str, Any]) -> bool:
        for rule in self.deduplication:
            if rule.type == "compare":
                query = Transaction.objects.all()

                # Build query conditions for each field in the rule
                for field, header in rule.fields.items():
                    if field in transaction_data:
                        if rule.match_type == "strict":
                            query = query.filter(**{field: transaction_data[field]})
                        else:  # lax matching
                            query = query.filter(
                                **{f"{field}__iexact": transaction_data[field]}
                            )

                # If we found any matching transaction, it's a duplicate
                if query.exists():
                    return True

        return False

    def _process_csv(self, file_path):
        with open(file_path, "r", encoding=self.settings.encoding) as csv_file:
            reader = csv.DictReader(csv_file, delimiter=self.settings.delimiter)

            # Count total rows
            self.import_run.total_rows = sum(1 for _ in reader)
            csv_file.seek(0)
            reader = csv.DictReader(csv_file, delimiter=self.settings.delimiter)

            self._log("info", f"Starting import with {self.import_run.total_rows} rows")

            # Skip specified number of rows
            for _ in range(self.settings.skip_rows):
                next(reader)

            if self.settings.skip_rows:
                self._log("info", f"Skipped {self.settings.skip_rows} initial rows")

            for row_number, row in enumerate(reader, start=1):
                try:
                    transaction_data = self._map_row_to_transaction(row)

                    if transaction_data:
                        if self.deduplication and self._check_duplicate_transaction(
                            transaction_data
                        ):
                            self.import_run.skipped_rows += 1
                            self._log("info", f"Skipped duplicate row {row_number}")
                            continue

                        self.import_run.transactions.add(transaction_data)
                        self.import_run.successful_rows += 1
                        self._log("debug", f"Successfully processed row {row_number}")

                    self.import_run.processed_rows += 1
                    self.import_run.save(
                        update_fields=[
                            "processed_rows",
                            "successful_rows",
                            "skipped_rows",
                        ]
                    )

                except Exception as e:
                    if not self.settings.skip_errors:
                        self._log(
                            "error",
                            f"Fatal error processing row {row_number}: {str(e)}",
                        )
                        self._update_status("FAILED")
                        raise
                    else:
                        self._log(
                            "warning", f"Error processing row {row_number}: {str(e)}"
                        )
                        self.import_run.failed_rows += 1
                        self.import_run.save(update_fields=["failed_rows"])

    def process_file(self, file_path: str):
        self._update_status("PROCESSING")
        self.import_run.started_at = timezone.now()
        self.import_run.save(update_fields=["started_at"])

        self._log("info", "Starting import process")

        try:
            if self.settings.file_type == "csv":
                self._process_csv(file_path)

            if self.import_run.processed_rows == self.import_run.total_rows:
                self._update_status("FINISHED")
                self._log(
                    "info",
                    f"Import completed successfully. "
                    f"Successful: {self.import_run.successful_rows}, "
                    f"Failed: {self.import_run.failed_rows}, "
                    f"Skipped: {self.import_run.skipped_rows}",
                )

        except Exception as e:
            self._update_status("FAILED")
            self._log("error", f"Import failed: {str(e)}")
            raise Exception("Import failed")

        finally:
            self._log("info", "Cleaning up temporary files")
            default_storage.delete(file_path)
            self.import_run.finished_at = timezone.now()
            self.import_run.save(update_fields=["finished_at"])
