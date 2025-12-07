from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from apps.import_app.models import ImportProfile, ImportRun


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
    WHITENOISE_AUTOREFRESH=True,
)
class ImportAPITests(TestCase):
    """Tests for the Import API endpoint"""

    def setUp(self):
        """Set up test data"""
        User = get_user_model()
        self.user = User.objects.create_user(
            email="testuser@test.com", password="testpass123"
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        # Create a basic import profile with minimal valid YAML config
        self.profile = ImportProfile.objects.create(
            name="Test Profile",
            version=ImportProfile.Versions.VERSION_1,
            yaml_config="""
file_type: csv
date_format: "%Y-%m-%d"
column_mapping:
  date:
    source: date
  description:
    source: description
  amount:
    source: amount
  transaction_type:
    detection_method: always_expense
  is_paid:
    detection_method: always_paid
  account:
    source: account
    match_field: name
""",
        )

    @patch("apps.import_app.tasks.process_import.defer")
    @patch("django.core.files.storage.FileSystemStorage.save")
    @patch("django.core.files.storage.FileSystemStorage.path")
    def test_create_import_success(self, mock_path, mock_save, mock_defer):
        """Test successful file upload creates ImportRun and queues task"""
        mock_save.return_value = "test_file.csv"
        mock_path.return_value = "/usr/src/app/temp/test_file.csv"

        csv_content = b"date,description,amount,account\n2025-01-01,Test,100,Main"
        file = SimpleUploadedFile(
            "test_file.csv", csv_content, content_type="text/csv"
        )

        response = self.client.post(
            "/api/import/import/",
            {"profile_id": self.profile.id, "file": file},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertIn("import_run_id", response.data)
        self.assertEqual(response.data["status"], "queued")

        # Verify ImportRun was created
        import_run = ImportRun.objects.get(id=response.data["import_run_id"])
        self.assertEqual(import_run.profile, self.profile)
        self.assertEqual(import_run.file_name, "test_file.csv")

        # Verify task was deferred
        mock_defer.assert_called_once_with(
            import_run_id=import_run.id,
            file_path="/usr/src/app/temp/test_file.csv",
            user_id=self.user.id,
        )

    def test_create_import_missing_profile(self):
        """Test request without profile_id returns 400"""
        csv_content = b"date,description,amount\n2025-01-01,Test,100"
        file = SimpleUploadedFile(
            "test_file.csv", csv_content, content_type="text/csv"
        )

        response = self.client.post(
            "/api/import/import/",
            {"file": file},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("profile_id", response.data)

    def test_create_import_missing_file(self):
        """Test request without file returns 400"""
        response = self.client.post(
            "/api/import/import/",
            {"profile_id": self.profile.id},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("file", response.data)

    def test_create_import_invalid_profile(self):
        """Test request with non-existent profile returns 400"""
        csv_content = b"date,description,amount\n2025-01-01,Test,100"
        file = SimpleUploadedFile(
            "test_file.csv", csv_content, content_type="text/csv"
        )

        response = self.client.post(
            "/api/import/import/",
            {"profile_id": 99999, "file": file},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("profile_id", response.data)

    @patch("apps.import_app.tasks.process_import.defer")
    @patch("django.core.files.storage.FileSystemStorage.save")
    @patch("django.core.files.storage.FileSystemStorage.path")
    def test_create_import_xlsx(self, mock_path, mock_save, mock_defer):
        """Test successful XLSX file upload"""
        mock_save.return_value = "test_file.xlsx"
        mock_path.return_value = "/usr/src/app/temp/test_file.xlsx"

        # Create a simple XLSX-like content (just for the upload test)
        xlsx_content = BytesIO(b"PK\x03\x04")  # XLSX files start with PK header
        file = SimpleUploadedFile(
            "test_file.xlsx",
            xlsx_content.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        response = self.client.post(
            "/api/import/import/",
            {"profile_id": self.profile.id, "file": file},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertIn("import_run_id", response.data)

    def test_unauthenticated_request(self):
        """Test unauthenticated request returns 403"""
        unauthenticated_client = APIClient()

        csv_content = b"date,description,amount\n2025-01-01,Test,100"
        file = SimpleUploadedFile(
            "test_file.csv", csv_content, content_type="text/csv"
        )

        response = unauthenticated_client.post(
            "/api/import/import/",
            {"profile_id": self.profile.id, "file": file},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
    WHITENOISE_AUTOREFRESH=True,
)
class ImportProfileAPITests(TestCase):
    """Tests for the Import Profile API endpoints"""

    def setUp(self):
        """Set up test data"""
        User = get_user_model()
        self.user = User.objects.create_user(
            email="testuser@test.com", password="testpass123"
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.profile1 = ImportProfile.objects.create(
            name="Profile 1",
            version=ImportProfile.Versions.VERSION_1,
            yaml_config="""
file_type: csv
date_format: "%Y-%m-%d"
column_mapping:
  date:
    source: date
  description:
    source: description
  amount:
    source: amount
  transaction_type:
    detection_method: always_expense
  is_paid:
    detection_method: always_paid
  account:
    source: account
    match_field: name
""",
        )
        self.profile2 = ImportProfile.objects.create(
            name="Profile 2",
            version=ImportProfile.Versions.VERSION_1,
            yaml_config="""
file_type: csv
date_format: "%Y-%m-%d"
column_mapping:
  date:
    source: date
  description:
    source: description
  amount:
    source: amount
  transaction_type:
    detection_method: always_income
  is_paid:
    detection_method: always_unpaid
  account:
    source: account
    match_field: name
""",
        )

    def test_list_profiles(self):
        """Test listing all profiles"""
        response = self.client.get("/api/import/profiles/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(len(response.data["results"]), 2)

    def test_retrieve_profile(self):
        """Test retrieving a specific profile"""
        response = self.client.get(f"/api/import/profiles/{self.profile1.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.profile1.id)
        self.assertEqual(response.data["name"], "Profile 1")
        self.assertIn("yaml_config", response.data)

    def test_retrieve_nonexistent_profile(self):
        """Test retrieving a non-existent profile returns 404"""
        response = self.client.get("/api/import/profiles/99999/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_profiles_unauthenticated(self):
        """Test unauthenticated request returns 403"""
        unauthenticated_client = APIClient()
        response = unauthenticated_client.get("/api/import/profiles/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
    WHITENOISE_AUTOREFRESH=True,
)
class ImportRunAPITests(TestCase):
    """Tests for the Import Run API endpoints"""

    def setUp(self):
        """Set up test data"""
        User = get_user_model()
        self.user = User.objects.create_user(
            email="testuser@test.com", password="testpass123"
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.profile1 = ImportProfile.objects.create(
            name="Profile 1",
            version=ImportProfile.Versions.VERSION_1,
            yaml_config="""
file_type: csv
date_format: "%Y-%m-%d"
column_mapping:
  date:
    source: date
  description:
    source: description
  amount:
    source: amount
  transaction_type:
    detection_method: always_expense
  is_paid:
    detection_method: always_paid
  account:
    source: account
    match_field: name
""",
        )
        self.profile2 = ImportProfile.objects.create(
            name="Profile 2",
            version=ImportProfile.Versions.VERSION_1,
            yaml_config="""
file_type: csv
date_format: "%Y-%m-%d"
column_mapping:
  date:
    source: date
  description:
    source: description
  amount:
    source: amount
  transaction_type:
    detection_method: always_income
  is_paid:
    detection_method: always_unpaid
  account:
    source: account
    match_field: name
""",
        )

        # Create import runs
        self.run1 = ImportRun.objects.create(
            profile=self.profile1,
            file_name="file1.csv",
            status=ImportRun.Status.FINISHED,
        )
        self.run2 = ImportRun.objects.create(
            profile=self.profile1,
            file_name="file2.csv",
            status=ImportRun.Status.QUEUED,
        )
        self.run3 = ImportRun.objects.create(
            profile=self.profile2,
            file_name="file3.csv",
            status=ImportRun.Status.FINISHED,
        )

    def test_list_all_runs(self):
        """Test listing all runs"""
        response = self.client.get("/api/import/runs/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 3)
        self.assertEqual(len(response.data["results"]), 3)

    def test_list_runs_by_profile(self):
        """Test filtering runs by profile_id"""
        response = self.client.get(f"/api/import/runs/?profile_id={self.profile1.id}")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)
        for run in response.data["results"]:
            self.assertEqual(run["profile"], self.profile1.id)

    def test_list_runs_by_other_profile(self):
        """Test filtering runs by another profile_id"""
        response = self.client.get(f"/api/import/runs/?profile_id={self.profile2.id}")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["profile"], self.profile2.id)

    def test_retrieve_run(self):
        """Test retrieving a specific run"""
        response = self.client.get(f"/api/import/runs/{self.run1.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.run1.id)
        self.assertEqual(response.data["file_name"], "file1.csv")
        self.assertEqual(response.data["status"], "FINISHED")

    def test_retrieve_nonexistent_run(self):
        """Test retrieving a non-existent run returns 404"""
        response = self.client.get("/api/import/runs/99999/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_runs_unauthenticated(self):
        """Test unauthenticated request returns 403"""
        unauthenticated_client = APIClient()
        response = unauthenticated_client.get("/api/import/runs/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
