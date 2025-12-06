from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import Account, AccountGroup
from apps.currencies.models import Currency
from apps.transactions.models import (
    Transaction,
    TransactionCategory,
    TransactionTag,
)


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
    WHITENOISE_AUTOREFRESH=True,
)
class TransactionSimpleAddViewTests(TestCase):
    """Tests for the transaction_simple_add view with query parameters"""

    def setUp(self):
        """Set up test data"""
        User = get_user_model()
        self.user = User.objects.create_user(
            email="testuser@test.com", password="testpass123"
        )
        self.client.login(username="testuser@test.com", password="testpass123")

        self.currency = Currency.objects.create(
            code="USD", name="US Dollar", decimal_places=2, prefix="$ "
        )
        self.account_group = AccountGroup.objects.create(name="Test Group")
        self.account = Account.objects.create(
            name="Test Account", group=self.account_group, currency=self.currency
        )
        self.category = TransactionCategory.objects.create(name="Test Category")
        self.tag = TransactionTag.objects.create(name="TestTag")

    def test_get_returns_form_with_default_values(self):
        """Test GET request returns 200 and form with defaults"""
        response = self.client.get("/add/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("form", response.context)

    def test_get_with_type_param(self):
        """Test type param sets form initial value"""
        response = self.client.get("/add/?type=EX")
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(form.initial.get("type"), Transaction.Type.EXPENSE)

    def test_get_with_account_param(self):
        """Test account param sets form initial value"""
        response = self.client.get(f"/add/?account={self.account.id}")
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(form.initial.get("account"), self.account.id)

    def test_get_with_is_paid_param_true(self):
        """Test is_paid param with true value"""
        response = self.client.get("/add/?is_paid=true")
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertTrue(form.initial.get("is_paid"))

    def test_get_with_is_paid_param_false(self):
        """Test is_paid param with false value"""
        response = self.client.get("/add/?is_paid=false")
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertFalse(form.initial.get("is_paid"))

    def test_get_with_amount_param(self):
        """Test amount param sets form initial value"""
        response = self.client.get("/add/?amount=150.50")
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(form.initial.get("amount"), "150.50")

    def test_get_with_description_param(self):
        """Test description param sets form initial value"""
        response = self.client.get("/add/?description=Test%20Transaction")
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(form.initial.get("description"), "Test Transaction")

    def test_get_with_notes_param(self):
        """Test notes param sets form initial value"""
        response = self.client.get("/add/?notes=Some%20notes")
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(form.initial.get("notes"), "Some notes")

    def test_get_with_category_param(self):
        """Test category param sets form initial value"""
        response = self.client.get(f"/add/?category={self.category.id}")
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(form.initial.get("category"), self.category.id)

    def test_get_with_tags_param(self):
        """Test tags param as comma-separated names"""
        response = self.client.get("/add/?tags=TestTag,AnotherTag")
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(form.initial.get("tags"), ["TestTag", "AnotherTag"])

    def test_get_with_all_params(self):
        """Test all params together work correctly"""
        url = (
            f"/add/?type=EX&account={self.account.id}&is_paid=true"
            f"&amount=200.00&description=Full%20Test&notes=Test%20notes"
            f"&category={self.category.id}&tags=TestTag"
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(form.initial.get("type"), Transaction.Type.EXPENSE)
        self.assertEqual(form.initial.get("account"), self.account.id)
        self.assertTrue(form.initial.get("is_paid"))
        self.assertEqual(form.initial.get("amount"), "200.00")
        self.assertEqual(form.initial.get("description"), "Full Test")
        self.assertEqual(form.initial.get("notes"), "Test notes")
        self.assertEqual(form.initial.get("category"), self.category.id)
        self.assertEqual(form.initial.get("tags"), ["TestTag"])

    def test_post_creates_transaction(self):
        """Test form submission creates transaction"""
        data = {
            "account": self.account.id,
            "type": "EX",
            "is_paid": True,
            "date": timezone.now().date().isoformat(),
            "amount": "100.00",
            "description": "Test Transaction",
        }
        response = self.client.post("/add/", data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            Transaction.objects.filter(description="Test Transaction").exists()
        )

    def test_get_with_date_param(self):
        """Test date param overrides expected date"""
        response = self.client.get("/add/?date=2025-06-15")
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(form.initial.get("date"), date(2025, 6, 15))

    def test_get_with_reference_date_param(self):
        """Test reference_date param sets form initial value"""
        response = self.client.get("/add/?reference_date=2025-07-01")
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(form.initial.get("reference_date"), date(2025, 7, 1))

    def test_get_with_account_name_param(self):
        """Test account param by name (case-insensitive)"""
        response = self.client.get("/add/?account=Test%20Account")
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(form.initial.get("account"), self.account.id)

    def test_get_with_category_name_param(self):
        """Test category param by name (case-insensitive)"""
        response = self.client.get("/add/?category=Test%20Category")
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(form.initial.get("category"), self.category.id)
