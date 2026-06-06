import shutil
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

from apps.accounts.models import Account
from apps.common.middleware.thread_local import delete_current_user, write_current_user
from apps.currencies.models import Currency
from apps.transactions.models import Transaction, TransactionAttachment
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
    WHITENOISE_AUTOREFRESH=True,
)
class TransactionAttachmentTests(TestCase):
    def setUp(self):
        self.attachment_media_root = tempfile.mkdtemp()
        self.override_private_media = override_settings(
            ATTACHMENT_MEDIA_ROOT=self.attachment_media_root
        )
        self.override_private_media.enable()
        self.addCleanup(self.override_private_media.disable)
        self.addCleanup(shutil.rmtree, self.attachment_media_root, ignore_errors=True)

        self.attachment_storage = TransactionAttachment._meta.get_field("file").storage
        self.original_storage_location = self.attachment_storage._location
        self.attachment_storage._location = self.attachment_media_root
        self.attachment_storage.__dict__.pop("base_location", None)
        self.attachment_storage.__dict__.pop("location", None)
        self.addCleanup(self.restore_attachment_storage)

        User = get_user_model()
        self.user1 = User.objects.create_user(
            email="user1@test.com", password="testpass123"
        )
        self.user2 = User.objects.create_user(
            email="user2@test.com", password="testpass123"
        )

        self.currency = Currency.objects.create(
            code="USD", name="US Dollar", decimal_places=2, prefix="$ "
        )
        self.user1_account = Account.all_objects.create(
            name="User1 Account", currency=self.currency, owner=self.user1
        )
        self.user2_account = Account.all_objects.create(
            name="User2 Account", currency=self.currency, owner=self.user2
        )
        self.transaction = Transaction.userless_all_objects.create(
            account=self.user1_account,
            type=Transaction.Type.EXPENSE,
            amount=Decimal("12.34"),
            is_paid=True,
            date=date(2026, 6, 5),
            description="Receipt transaction",
            owner=self.user1,
        )
        self.other_transaction = Transaction.userless_all_objects.create(
            account=self.user2_account,
            type=Transaction.Type.EXPENSE,
            amount=Decimal("56.78"),
            is_paid=True,
            date=date(2026, 6, 5),
            description="Other receipt transaction",
            owner=self.user2,
        )

    def restore_attachment_storage(self):
        self.attachment_storage._location = self.original_storage_location
        self.attachment_storage.__dict__.pop("base_location", None)
        self.attachment_storage.__dict__.pop("location", None)

    def test_attachment_uses_uuid_and_preserves_original_download_name(self):
        attachment = TransactionAttachment.objects.create(
            transaction=self.transaction,
            file=SimpleUploadedFile(
                "receipt June.pdf", b"receipt bytes", content_type="application/pdf"
            ),
            uploaded_by=self.user1,
        )

        self.assertEqual(attachment.original_name, "receipt June.pdf")
        self.assertNotIn("receipt June.pdf", attachment.file.name)

        self.client.force_login(self.user1)
        response = self.client.get(
            reverse(
                "transaction_attachment_download",
                kwargs={"attachment_id": attachment.id},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"receipt bytes")
        self.assertIn('filename="receipt June.pdf"', response["Content-Disposition"])

    def test_user_without_transaction_access_cannot_download_attachment(self):
        attachment = TransactionAttachment.objects.create(
            transaction=self.other_transaction,
            file=SimpleUploadedFile("private.txt", b"private"),
            uploaded_by=self.user2,
        )

        self.client.force_login(self.user1)
        response = self.client.get(
            reverse(
                "transaction_attachment_download",
                kwargs={"attachment_id": attachment.id},
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_attachment_button_lives_in_transaction_hover_toolbar(self):
        template = Path("templates/cotton/transaction/item.html").read_text()
        before_toolbar, toolbar = template.split("{#      Item actions#}", 1)

        self.assertNotIn("transaction_attachments", before_toolbar)
        self.assertLess(
            toolbar.index("transaction_edit"),
            toolbar.index("transaction_attachments"),
        )
        self.assertLess(
            toolbar.index("transaction_attachments"),
            toolbar.index("transaction_delete"),
        )

    def test_transaction_edit_form_does_not_include_attachment_upload(self):
        self.client.force_login(self.user1)

        response = self.client.get(
            reverse("transaction_edit", kwargs={"transaction_id": self.transaction.id}),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "multipart/form-data")
        self.assertNotContains(response, 'type="file"')

    def test_attachment_management_uploads_multiple_attachments(self):
        self.client.force_login(self.user1)

        response = self.client.post(
            reverse(
                "transaction_attachments",
                kwargs={"transaction_id": self.transaction.id},
            ),
            {
                "attachments": [
                    SimpleUploadedFile("first.txt", b"first"),
                    SimpleUploadedFile("second.txt", b"second"),
                ],
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "first.txt")
        self.assertContains(response, "second.txt")
        self.assertEqual(self.transaction.attachments.count(), 2)

    def test_attachment_delete_returns_refreshed_attachment_list(self):
        attachment = TransactionAttachment.objects.create(
            transaction=self.transaction,
            file=SimpleUploadedFile("delete-me.txt", b"delete"),
            uploaded_by=self.user1,
        )

        self.client.force_login(self.user1)
        response = self.client.delete(
            reverse(
                "transaction_attachment_delete",
                kwargs={"attachment_id": attachment.id},
            ),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "delete-me.txt")
        self.assertContains(response, "No attachments yet")
        self.assertFalse(
            TransactionAttachment.objects.filter(id=attachment.id).exists()
        )

    def test_hard_deleting_transaction_deletes_attachment_files(self):
        attachment = TransactionAttachment.objects.create(
            transaction=self.transaction,
            file=SimpleUploadedFile("hard-delete.txt", b"delete with transaction"),
            uploaded_by=self.user1,
        )
        file_path = Path(attachment.file.path)

        self.assertTrue(file_path.exists())

        write_current_user(self.user1)
        self.addCleanup(delete_current_user)

        self.transaction.delete()

        self.assertTrue(file_path.exists())
        self.assertTrue(TransactionAttachment.objects.filter(id=attachment.id).exists())

        self.transaction.delete()

        self.assertFalse(file_path.exists())
        self.assertFalse(
            TransactionAttachment.objects.filter(id=attachment.id).exists()
        )
