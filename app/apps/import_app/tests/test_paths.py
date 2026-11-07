"""Tests for the folders import code reads from and writes to."""

import json
import os
import runpy
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.import_app.models import ImportRun
from apps.import_app.services import PresetService
from apps.import_app.services.v1 import ImportService
from apps.import_app.tests.test_view_permissions import (
    HTMX,
    ImportObjectPermissionTestCase,
)


def load_settings(**env):
    """Evaluates the settings module from scratch under the given env vars."""
    with patch.dict(os.environ, env):
        return runpy.run_path(str(Path(settings.BASE_DIR) / "WYGIWYH" / "settings.py"))


class PathSettingsTests(SimpleTestCase):
    def test_defaults_match_the_docker_image_layout(self):
        loaded = load_settings(IMPORT_TEMP_ROOT="", CACHE_ROOT="")

        base_dir = loaded["BASE_DIR"]
        self.assertEqual(loaded["IMPORT_TEMP_ROOT"], base_dir / "temp")
        self.assertEqual(loaded["IMPORT_PRESETS_ROOT"], base_dir / "import_presets")
        self.assertEqual(
            loaded["CACHES"]["default"]["LOCATION"],
            Path("/var/tmp/django_cache").resolve(),
        )
        self.assertEqual(
            loaded["CACHES"]["update_check"]["LOCATION"],
            Path("/var/tmp/django_cache_update_check").resolve(),
        )

    def test_env_vars_move_temp_and_cache_folders(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root).resolve()
            loaded = load_settings(
                IMPORT_TEMP_ROOT=str(root / "uploads"), CACHE_ROOT=str(root / "cache")
            )

        self.assertEqual(loaded["IMPORT_TEMP_ROOT"], root / "uploads")
        self.assertEqual(
            loaded["CACHES"]["default"]["LOCATION"], root / "cache" / "django_cache"
        )
        self.assertEqual(
            loaded["CACHES"]["update_check"]["LOCATION"],
            root / "cache" / "django_cache_update_check",
        )


class PresetServiceTests(SimpleTestCase):
    def test_lists_the_presets_shipped_with_the_app(self):
        folder_names = {
            preset["folder_name"] for preset in PresetService.get_all_presets()
        }

        self.assertIn("qif_standard", folder_names)

    def test_reads_presets_from_configured_folder(self):
        with tempfile.TemporaryDirectory() as root:
            preset = Path(root) / "my_bank"
            preset.mkdir()
            (preset / "manifest.json").write_text(json.dumps({"name": "My Bank"}))
            (preset / "config.yml").write_text("settings: {}")

            with override_settings(IMPORT_PRESETS_ROOT=Path(root)):
                presets = PresetService.get_all_presets()

        self.assertEqual([p["name"] for p in presets], ["My Bank"])


class ImportTempRootTests(ImportObjectPermissionTestCase):
    def setUp(self):
        super().setUp()
        self.temp_root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.temp_root, ignore_errors=True)
        temp_root_override = override_settings(IMPORT_TEMP_ROOT=self.temp_root)
        temp_root_override.enable()
        self.addCleanup(temp_root_override.disable)

    @patch("apps.import_app.views.process_import.defer")
    def test_web_upload_is_stored_in_temp_root(self, mock_defer):
        self.login(self.owner)
        response = self.client.post(
            reverse("import_run_add", kwargs={"profile_id": self.private_profile.id}),
            {"file": SimpleUploadedFile("web.csv", b"date,amount\n")},
            **HTMX,
        )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(
            mock_defer.call_args.kwargs["file_path"], str(self.temp_root / "web.csv")
        )
        self.assertTrue((self.temp_root / "web.csv").is_file())

    @patch("apps.api.views.imports.process_import.defer")
    def test_api_upload_is_stored_in_temp_root(self, mock_defer):
        client = APIClient()
        client.force_authenticate(user=self.owner)
        response = client.post(
            "/api/import/import/",
            {
                "profile_id": self.private_profile.id,
                "file": SimpleUploadedFile("api.csv", b"date,amount\n"),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(
            mock_defer.call_args.kwargs["file_path"], str(self.temp_root / "api.csv")
        )
        self.assertTrue((self.temp_root / "api.csv").is_file())

    def _service(self):
        run = ImportRun.objects.create(
            profile=self.private_profile, file_name="file.csv", owner=self.owner
        )
        return ImportService(run)

    def test_service_accepts_files_inside_temp_root(self):
        path = str(self.temp_root / "file.csv")

        self.assertEqual(self._service()._validate_file_path(path), path)

    def test_service_rejects_files_outside_temp_root(self):
        service = self._service()

        for path in (
            "/etc/passwd",
            self.temp_root / ".." / "file.csv",
            # Shares the temp root as a string prefix, but is a different folder
            f"{self.temp_root}-other/file.csv",
        ):
            with self.subTest(path=path), self.assertRaises(ValueError):
                service._validate_file_path(str(path))
