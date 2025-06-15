from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from unittest.mock import patch, MagicMock
from io import BytesIO
import zipfile # Added for zip file creation
from django.core.files.uploadedfile import InMemoryUploadedFile # Added for file upload testing

# Dataset from tablib is not directly imported, its behavior will be mocked.
# Resource classes are also mocked by path string.

from apps.export_app.forms import ExportForm, RestoreForm # Added RestoreForm


class ExportAppTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='super',
            email='super@example.com',
            password='password'
        )
        self.client = Client()
        self.client.login(username='super', password='password')

    @patch('apps.export_app.views.UserResource')
    def test_export_form_single_selection_csv_response(self, mock_UserResource):
        # Configure the mock UserResource
        mock_user_resource_instance = mock_UserResource.return_value

        # Mock the export() method's return value (which is a Dataset object)
        # Then, mock the 'csv' attribute of this Dataset object
        mock_dataset = MagicMock() # Using MagicMock for the dataset
        mock_dataset.csv = "user_id,username\n1,testuser"
        mock_user_resource_instance.export.return_value = mock_dataset

        post_data = {'users': True} # Other fields default to False or their initial values

        response = self.client.post(reverse('export_app:export_form'), data=post_data)

        mock_user_resource_instance.export.assert_called_once()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn("attachment; filename=", response['Content-Disposition'])
        self.assertIn(".csv", response['Content-Disposition'])
        # Check if the filename contains 'users'
        self.assertIn("users_export_", response['Content-Disposition'].lower())
        self.assertEqual(response.content.decode(), "user_id,username\n1,testuser")

    @patch('apps.export_app.views.AccountResource') # Mock AccountResource first
    @patch('apps.export_app.views.UserResource')   # Then UserResource
    def test_export_form_multiple_selections_zip_response(self, mock_UserResource, mock_AccountResource):
        # Configure UserResource mock
        mock_user_instance = mock_UserResource.return_value
        mock_user_dataset = MagicMock()
        mock_user_dataset.csv = "user_data_here"
        mock_user_instance.export.return_value = mock_user_dataset

        # Configure AccountResource mock
        mock_account_instance = mock_AccountResource.return_value
        mock_account_dataset = MagicMock()
        mock_account_dataset.csv = "account_data_here"
        mock_account_instance.export.return_value = mock_account_dataset

        post_data = {
            'users': True,
            'accounts': True
            # other fields default to False or their initial values
        }

        response = self.client.post(reverse('export_app:export_form'), data=post_data)

        mock_user_instance.export.assert_called_once()
        mock_account_instance.export.assert_called_once()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/zip')
        self.assertIn("attachment; filename=", response['Content-Disposition'])
        self.assertIn(".zip", response['Content-Disposition'])
        # Add zip file content check if possible and required later

    def test_export_form_no_selection(self):
        # Get all field names from ExportForm and set them to False
        # This ensures that if new export options are added, this test still tries to unselect them.
        form_fields = ExportForm.base_fields.keys()
        post_data = {field: False for field in form_fields}

        response = self.client.post(reverse('export_app:export_form'), data=post_data)

        self.assertEqual(response.status_code, 200)
        # The expected message is "You have to select at least one export"
        # This message is translatable, so using _() for comparison if the view returns translated string.
        # The view returns HttpResponse(_("You have to select at least one export"))
        self.assertEqual(response.content.decode('utf-8'), _("You have to select at least one export"))

    # Placeholder for zip content check, if to be implemented
    # import zipfile
    # def test_zip_contents(self):
    #     # ... (setup response with zip data) ...
    #     with zipfile.ZipFile(BytesIO(response.content), 'r') as zipf:
    #         self.assertIn('users.csv', zipf.namelist())
    #         self.assertIn('accounts.csv', zipf.namelist())
    #         user_csv_content = zipf.read('users.csv').decode()
    #         self.assertEqual(user_csv_content, "user_data_here")
    #         account_csv_content = zipf.read('accounts.csv').decode()
    #         self.assertEqual(account_csv_content, "account_data_here")

    @patch('apps.export_app.views.process_imports')
    def test_import_form_valid_zip_calls_process_imports(self, mock_process_imports):
        # Create a mock ZIP file content
        zip_content_buffer = BytesIO()
        with zipfile.ZipFile(zip_content_buffer, 'w') as zf:
            zf.writestr('dummy.csv', 'some,data')
        zip_content_buffer.seek(0)

        # Create an InMemoryUploadedFile instance
        mock_zip_file = InMemoryUploadedFile(
            zip_content_buffer,
            'zip_file',  # field_name
            'test_export.zip',  # file_name
            'application/zip',  # content_type
            zip_content_buffer.getbuffer().nbytes,  # size
            None  # charset
        )

        post_data = {'zip_file': mock_zip_file}
        url = reverse('export_app:restore_form')

        response = self.client.post(url, data=post_data, format='multipart')

        mock_process_imports.assert_called_once()
        # Check the second argument passed to process_imports (the form's cleaned_data['zip_file'])
        # The first argument (args[0]) is the request object.
        # The second argument (args[1]) is the form instance.
        # We need to check the 'zip_file' attribute of the cleaned_data of the form instance.
        # However, it's simpler to check the UploadedFile object directly if that's what process_imports receives.
        # Based on the task: "The second argument to process_imports is form.cleaned_data['zip_file']"
        # This means that process_imports is called as process_imports(request, form.cleaned_data['zip_file'], ...)
        # Let's assume process_imports signature is process_imports(request, file_obj, ...)
        # So, call_args[0][1] would be the file_obj.

        # Actually, the view calls process_imports(request, form)
        # So, we check form.cleaned_data['zip_file'] on the passed form instance
        called_form_instance = mock_process_imports.call_args[0][1] # The form instance
        self.assertEqual(called_form_instance.cleaned_data['zip_file'], mock_zip_file)

        self.assertEqual(response.status_code, 204)
        # The HX-Trigger header might have multiple values, ensure both are present
        self.assertIn("hide_offcanvas", response.headers['HX-Trigger'])
        self.assertIn("updated", response.headers['HX-Trigger'])


    def test_import_form_no_file_selected(self):
        post_data = {} # No file selected
        url = reverse('export_app:restore_form')

        response = self.client.post(url, data=post_data)

        self.assertEqual(response.status_code, 200) # Form re-rendered with errors
        # Check that the specific error message from RestoreForm.clean() is present
        expected_error_message = _("Please upload either a ZIP file or at least one CSV file")
        self.assertContains(response, expected_error_message)
        # Also check for the HX-Trigger which is always set
        self.assertIn("updated", response.headers['HX-Trigger'])
