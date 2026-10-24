"""Object-level authorization tests for import profiles and import runs.

Regression coverage for GHSA-q668-h56g-mfp4: ImportProfile and ImportRun had no
owner, and neither the web views nor the REST viewsets filtered by the
requesting user, so any authenticated user could read, edit and delete every
other user's profiles and runs.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.import_app.models import ImportProfile, ImportRun

HTMX = {"HTTP_HX_REQUEST": "true"}

YAML_CONFIG = """
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
"""


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
    WHITENOISE_AUTOREFRESH=True,
    DEMO=False,
)
class ImportObjectPermissionTestCase(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="owner@test.com", password="testpass123"
        )
        self.shared_user = User.objects.create_user(
            email="shared@test.com", password="testpass123"
        )
        self.stranger = User.objects.create_user(
            email="stranger@test.com", password="testpass123"
        )

        # Private and unshared: invisible to everyone but the owner.
        self.private_profile = ImportProfile.all_objects.create(
            name="Private profile",
            yaml_config=YAML_CONFIG,
            owner=self.owner,
            visibility="private",
        )
        # Private but shared with shared_user: usable by them, not by stranger.
        self.shared_profile = ImportProfile.all_objects.create(
            name="Shared profile",
            yaml_config=YAML_CONFIG,
            owner=self.owner,
            visibility="private",
        )
        self.shared_profile.shared_with.add(self.shared_user)
        # Legacy profile created before profiles had owners.
        self.unowned_profile = ImportProfile.all_objects.create(
            name="Unowned profile", yaml_config=YAML_CONFIG, owner=None
        )

        self.owner_run = ImportRun.all_objects.create(
            profile=self.shared_profile,
            file_name="owner-statement.csv",
            logs="owner log",
            owner=self.owner,
        )
        self.shared_user_run = ImportRun.all_objects.create(
            profile=self.shared_profile,
            file_name="shared-user-statement.csv",
            logs="shared user log",
            owner=self.shared_user,
        )

    def login(self, user):
        self.client.force_login(user)


class ImportProfileViewPermissionTests(ImportObjectPermissionTestCase):
    def test_list_only_shows_visible_profiles(self):
        self.login(self.stranger)
        response = self.client.get(reverse("import_profiles_list"), **HTMX)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Private profile")
        self.assertNotContains(response, "Shared profile")
        self.assertContains(response, "Unowned profile")

    def test_list_shows_profiles_shared_with_user(self):
        self.login(self.shared_user)
        response = self.client.get(reverse("import_profiles_list"), **HTMX)

        self.assertContains(response, "Shared profile")
        self.assertNotContains(response, "Private profile")

    def test_stranger_cannot_edit_private_profile(self):
        self.login(self.stranger)
        response = self.client.post(
            reverse(
                "import_profile_edit", kwargs={"profile_id": self.private_profile.id}
            ),
            {"name": "Hijacked", "version": 1, "yaml_config": YAML_CONFIG},
            **HTMX,
        )

        self.assertEqual(response.status_code, 404)
        self.private_profile.refresh_from_db()
        self.assertEqual(self.private_profile.name, "Private profile")

    def test_shared_user_cannot_edit_shared_profile(self):
        self.login(self.shared_user)
        response = self.client.post(
            reverse(
                "import_profile_edit", kwargs={"profile_id": self.shared_profile.id}
            ),
            {"name": "Hijacked", "version": 1, "yaml_config": YAML_CONFIG},
            **HTMX,
        )

        self.assertEqual(response.status_code, 403)
        self.shared_profile.refresh_from_db()
        self.assertEqual(self.shared_profile.name, "Shared profile")

    def test_owner_can_edit_profile(self):
        self.login(self.owner)
        response = self.client.post(
            reverse(
                "import_profile_edit", kwargs={"profile_id": self.private_profile.id}
            ),
            {
                "name": "Renamed",
                "version": 1,
                "yaml_config": YAML_CONFIG,
                "submit": "Update",
            },
            **HTMX,
        )

        self.assertEqual(response.status_code, 204)
        self.private_profile.refresh_from_db()
        self.assertEqual(self.private_profile.name, "Renamed")

    def test_stranger_cannot_delete_private_profile(self):
        self.login(self.stranger)
        response = self.client.delete(
            reverse(
                "import_profile_delete",
                kwargs={"profile_id": self.private_profile.id},
            ),
            **HTMX,
        )

        self.assertEqual(response.status_code, 404)
        self.assertTrue(
            ImportProfile.all_objects.filter(id=self.private_profile.id).exists()
        )

    def test_shared_user_delete_only_removes_their_access(self):
        self.login(self.shared_user)
        response = self.client.delete(
            reverse(
                "import_profile_delete", kwargs={"profile_id": self.shared_profile.id}
            ),
            **HTMX,
        )

        self.assertEqual(response.status_code, 204)
        self.assertTrue(
            ImportProfile.all_objects.filter(id=self.shared_profile.id).exists()
        )
        self.assertFalse(
            self.shared_profile.shared_with.filter(pk=self.shared_user.pk).exists()
        )
        self.assertTrue(
            ImportRun.all_objects.filter(id=self.owner_run.id).exists()
        )

    def test_owner_can_delete_profile(self):
        self.login(self.owner)
        response = self.client.delete(
            reverse(
                "import_profile_delete",
                kwargs={"profile_id": self.private_profile.id},
            ),
            **HTMX,
        )

        self.assertEqual(response.status_code, 204)
        self.assertFalse(
            ImportProfile.all_objects.filter(id=self.private_profile.id).exists()
        )

    def test_shared_user_cannot_change_share_settings(self):
        self.login(self.shared_user)
        response = self.client.post(
            reverse(
                "import_profile_share_settings", kwargs={"pk": self.shared_profile.id}
            ),
            {"owner": self.shared_user.id, "visibility": "public"},
            **HTMX,
        )

        self.assertEqual(response.status_code, 403)
        self.shared_profile.refresh_from_db()
        self.assertEqual(self.shared_profile.owner, self.owner)

    def test_take_ownership_of_unowned_profile(self):
        self.login(self.stranger)
        response = self.client.get(
            reverse(
                "import_profile_take_ownership",
                kwargs={"profile_id": self.unowned_profile.id},
            ),
            **HTMX,
        )

        self.assertEqual(response.status_code, 204)
        self.unowned_profile.refresh_from_db()
        self.assertEqual(self.unowned_profile.owner, self.stranger)

    def test_cannot_take_ownership_of_owned_profile(self):
        self.login(self.shared_user)
        response = self.client.get(
            reverse(
                "import_profile_take_ownership",
                kwargs={"profile_id": self.shared_profile.id},
            ),
            **HTMX,
        )

        self.assertEqual(response.status_code, 403)
        self.shared_profile.refresh_from_db()
        self.assertEqual(self.shared_profile.owner, self.owner)


class ImportRunViewPermissionTests(ImportObjectPermissionTestCase):
    def test_runs_list_only_shows_own_runs(self):
        self.login(self.shared_user)
        response = self.client.get(
            reverse(
                "import_profile_runs_list",
                kwargs={"profile_id": self.shared_profile.id},
            ),
            **HTMX,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "shared-user-statement.csv")
        self.assertNotContains(response, "owner-statement.csv")

    def test_stranger_cannot_list_runs_of_private_profile(self):
        self.login(self.stranger)
        response = self.client.get(
            reverse(
                "import_profile_runs_list",
                kwargs={"profile_id": self.shared_profile.id},
            ),
            **HTMX,
        )

        self.assertEqual(response.status_code, 404)

    def test_cannot_read_another_users_run_log(self):
        self.login(self.shared_user)
        response = self.client.get(
            reverse(
                "import_run_log",
                kwargs={
                    "profile_id": self.shared_profile.id,
                    "run_id": self.owner_run.id,
                },
            ),
            **HTMX,
        )

        self.assertEqual(response.status_code, 404)

    def test_cannot_delete_another_users_run(self):
        self.login(self.shared_user)
        response = self.client.delete(
            reverse(
                "import_run_delete",
                kwargs={
                    "profile_id": self.shared_profile.id,
                    "run_id": self.owner_run.id,
                },
            ),
            **HTMX,
        )

        self.assertEqual(response.status_code, 404)
        self.assertTrue(ImportRun.all_objects.filter(id=self.owner_run.id).exists())

    def test_owner_can_delete_own_run(self):
        self.login(self.shared_user)
        response = self.client.delete(
            reverse(
                "import_run_delete",
                kwargs={
                    "profile_id": self.shared_profile.id,
                    "run_id": self.shared_user_run.id,
                },
            ),
            **HTMX,
        )

        self.assertEqual(response.status_code, 204)
        self.assertFalse(
            ImportRun.all_objects.filter(id=self.shared_user_run.id).exists()
        )

    def test_stranger_cannot_import_with_private_profile(self):
        self.login(self.stranger)
        response = self.client.get(
            reverse("import_run_add", kwargs={"profile_id": self.private_profile.id}),
            **HTMX,
        )

        self.assertEqual(response.status_code, 404)

    @patch("apps.import_app.views.process_import.defer")
    @patch("apps.import_app.views.FileSystemStorage.save", return_value="file.csv")
    @patch("apps.import_app.views.FileSystemStorage.path", return_value="/tmp/file.csv")
    def test_import_with_shared_profile_is_owned_by_uploader(
        self, mock_path, mock_save, mock_defer
    ):
        self.login(self.shared_user)
        response = self.client.post(
            reverse("import_run_add", kwargs={"profile_id": self.shared_profile.id}),
            {"file": SimpleUploadedFile("file.csv", b"date,amount\n")},
            **HTMX,
        )

        self.assertEqual(response.status_code, 204)
        run = ImportRun.all_objects.latest("id")
        self.assertEqual(run.owner, self.shared_user)
        self.assertEqual(run.profile, self.shared_profile)


class ImportAPIPermissionTests(ImportObjectPermissionTestCase):
    def setUp(self):
        super().setUp()
        self.api = APIClient()

    def test_profiles_list_only_returns_visible_profiles(self):
        self.api.force_authenticate(user=self.stranger)
        response = self.api.get("/api/import/profiles/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = {p["name"] for p in response.data["results"]}
        self.assertEqual(names, {"Unowned profile"})

    def test_cannot_retrieve_private_profile(self):
        self.api.force_authenticate(user=self.stranger)
        response = self.api.get(f"/api/import/profiles/{self.private_profile.id}/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_runs_list_only_returns_own_runs(self):
        self.api.force_authenticate(user=self.stranger)
        response = self.api.get("/api/import/runs/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)

    def test_runs_list_on_shared_profile_hides_other_users_runs(self):
        self.api.force_authenticate(user=self.shared_user)
        response = self.api.get(
            "/api/import/runs/", {"profile_id": self.shared_profile.id}
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {r["id"] for r in response.data["results"]}
        self.assertEqual(ids, {self.shared_user_run.id})

    def test_cannot_retrieve_another_users_run(self):
        self.api.force_authenticate(user=self.stranger)
        response = self.api.get(f"/api/import/runs/{self.owner_run.id}/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cannot_import_with_private_profile(self):
        self.api.force_authenticate(user=self.stranger)
        response = self.api.post(
            "/api/import/import/",
            {
                "profile_id": self.private_profile.id,
                "file": SimpleUploadedFile("file.csv", b"date,amount\n"),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("profile_id", response.data)

    @patch("apps.import_app.tasks.process_import.defer")
    @patch("django.core.files.storage.FileSystemStorage.save", return_value="file.csv")
    @patch("django.core.files.storage.FileSystemStorage.path", return_value="/tmp/file.csv")
    def test_import_with_shared_profile_is_owned_by_uploader(
        self, mock_path, mock_save, mock_defer
    ):
        self.api.force_authenticate(user=self.shared_user)
        response = self.api.post(
            "/api/import/import/",
            {
                "profile_id": self.shared_profile.id,
                "file": SimpleUploadedFile("file.csv", b"date,amount\n"),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        run = ImportRun.all_objects.get(id=response.data["import_run_id"])
        self.assertEqual(run.owner, self.shared_user)
