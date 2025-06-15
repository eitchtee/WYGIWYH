import csv
import io
import zipfile
from decimal import Decimal
from datetime import date, datetime

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Account, AccountGroup
from apps.currencies.models import Currency
from apps.transactions.models import Transaction, TransactionCategory, TransactionTag, TransactionEntity
from apps.export_app.resources.transactions import TransactionResource, TransactionTagResource
from apps.export_app.resources.accounts import AccountResource
from apps.export_app.forms import ExportForm, RestoreForm # Added RestoreForm

User = get_user_model()

class BaseExportAppTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            email="exportadmin@example.com", password="password"
        )
        cls.currency_usd = Currency.objects.create(code="USD", name="US Dollar", decimal_places=2)
        cls.currency_eur = Currency.objects.create(code="EUR", name="Euro", decimal_places=2)

        cls.user_group = AccountGroup.objects.create(name="User Group", owner=cls.superuser)
        cls.account_usd = Account.objects.create(
            name="Checking USD", currency=cls.currency_usd, owner=cls.superuser, group=cls.user_group
        )
        cls.account_eur = Account.objects.create(
            name="Savings EUR", currency=cls.currency_eur, owner=cls.superuser, group=cls.user_group
        )

        cls.category_food = TransactionCategory.objects.create(name="Food", owner=cls.superuser)
        cls.tag_urgent = TransactionTag.objects.create(name="Urgent", owner=cls.superuser)
        cls.entity_store = TransactionEntity.objects.create(name="SuperStore", owner=cls.superuser)

        cls.transaction1 = Transaction.objects.create(
            account=cls.account_usd,
            owner=cls.superuser,
            type=Transaction.Type.EXPENSE,
            date=date(2023, 1, 10),
            reference_date=date(2023, 1, 1),
            amount=Decimal("50.00"),
            description="Groceries",
            category=cls.category_food,
            is_paid=True
        )
        cls.transaction1.tags.add(cls.tag_urgent)
        cls.transaction1.entities.add(cls.entity_store)

        cls.transaction2 = Transaction.objects.create(
            account=cls.account_eur,
            owner=cls.superuser,
            type=Transaction.Type.INCOME,
            date=date(2023, 1, 15),
            reference_date=date(2023, 1, 1),
            amount=Decimal("1200.00"),
            description="Salary",
            is_paid=True
        )

    def setUp(self):
        self.client = Client()
        self.client.login(email="exportadmin@example.com", password="password")


class ResourceExportTests(BaseExportAppTest):
    def test_transaction_resource_export(self):
        resource = TransactionResource()
        queryset = Transaction.objects.filter(owner=self.superuser).order_by('pk') # Ensure consistent order
        dataset = resource.export(queryset=queryset)

        self.assertEqual(len(dataset), 2)
        self.assertIn("id", dataset.headers)
        self.assertIn("account", dataset.headers)
        self.assertIn("description", dataset.headers)
        self.assertIn("category", dataset.headers)
        self.assertIn("tags", dataset.headers)
        self.assertIn("entities", dataset.headers)

        exported_row1_dict = dict(zip(dataset.headers, dataset[0]))

        self.assertEqual(exported_row1_dict["id"], self.transaction1.id)
        self.assertEqual(exported_row1_dict["account"], self.account_usd.name)
        self.assertEqual(exported_row1_dict["description"], "Groceries")
        self.assertEqual(exported_row1_dict["category"], self.category_food.name)
        # M2M fields order might vary, so check for presence
        self.assertIn(self.tag_urgent.name, exported_row1_dict["tags"].split(','))
        self.assertIn(self.entity_store.name, exported_row1_dict["entities"].split(','))
        self.assertEqual(Decimal(exported_row1_dict["amount"]), self.transaction1.amount)


    def test_account_resource_export(self):
        resource = AccountResource()
        queryset = Account.objects.filter(owner=self.superuser).order_by('name') # Ensure consistent order
        dataset = resource.export(queryset=queryset)

        self.assertEqual(len(dataset), 2)
        self.assertIn("id", dataset.headers)
        self.assertIn("name", dataset.headers)
        self.assertIn("group", dataset.headers)
        self.assertIn("currency", dataset.headers)

        # Assuming order by name, Checking USD comes first
        exported_row_usd_dict = dict(zip(dataset.headers, dataset[0]))
        self.assertEqual(exported_row_usd_dict["name"], self.account_usd.name)
        self.assertEqual(exported_row_usd_dict["group"], self.user_group.name)
        self.assertEqual(exported_row_usd_dict["currency"], self.currency_usd.name)


class ExportViewTests(BaseExportAppTest):
    def test_export_form_get(self):
        response = self.client.get(reverse("export_form"))
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.context["form"], ExportForm)

    def test_export_single_csv(self):
        data = {"transactions": "on"}
        response = self.client.post(reverse("export_form"), data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertTrue(response["Content-Disposition"].endswith("_WYGIWYH_export_transactions.csv\""))

        content = response.content.decode('utf-8')
        reader = csv.reader(io.StringIO(content))
        headers = next(reader)
        self.assertIn("id", headers)
        self.assertIn("description", headers)

        self.assertIn(self.transaction1.description, content)
        self.assertIn(self.transaction2.description, content)


    def test_export_multiple_to_zip(self):
        data = {
            "transactions": "on",
            "accounts": "on",
        }
        response = self.client.post(reverse("export_form"), data)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/zip")
        self.assertTrue(response["Content-Disposition"].endswith("_WYGIWYH_export.zip\""))

        zip_buffer = io.BytesIO(response.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            filenames = zf.namelist()
            self.assertIn("transactions.csv", filenames)
            self.assertIn("accounts.csv", filenames)

            with zf.open("transactions.csv") as csv_file:
                content = csv_file.read().decode('utf-8')
                self.assertIn("id,type,date", content)
                self.assertIn(self.transaction1.description, content)


    def test_export_no_selection(self):
        data = {}
        response = self.client.post(reverse("export_form"), data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("You have to select at least one export", response.content.decode())

    def test_export_access_non_superuser(self):
        normal_user = User.objects.create_user(email="normal@example.com", password="password")
        self.client.logout()
        self.client.login(email="normal@example.com", password="password")

        response = self.client.get(reverse("export_index"))
        self.assertEqual(response.status_code, 302)

        response = self.client.get(reverse("export_form"))
        self.assertEqual(response.status_code, 302)


class RestoreViewTests(BaseExportAppTest):
    def test_restore_form_get(self):
        response = self.client.get(reverse("restore_form"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "export_app/fragments/restore.html")
        self.assertIsInstance(response.context["form"], RestoreForm)

    # Actual restore POST tests are complex due to file processing and DB interactions.
    # A placeholder for how one might start, heavily reliant on mocking or a working DB.
    # @patch('apps.export_app.views.process_imports')
    # def test_restore_form_post_zip_mocked_processing(self, mock_process_imports):
    #     zip_content = io.BytesIO()
    #     with zipfile.ZipFile(zip_content, "w") as zf:
    #        zf.writestr("users.csv", "id,email\n1,test@example.com") # Minimal valid CSV content

    #     zip_file_upload = SimpleUploadedFile("test_restore.zip", zip_content.getvalue(), content_type="application/zip")
    #     data = {"zip_file": zip_file_upload}

    #     response = self.client.post(reverse("restore_form"), data)
    #     self.assertEqual(response.status_code, 204) # Expecting HTMX success
    #     mock_process_imports.assert_called_once()
    #     # Further checks on how mock_process_imports was called could be added here.
    pass
```
