from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Account, AccountGroup
from apps.currencies.models import Currency
from apps.transactions.models import (
    InstallmentPlan,
    QuickTransaction,
    RecurringTransaction,
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


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
    WHITENOISE_AUTOREFRESH=True,
)
class TransactionConvertViewTests(TestCase):
    """Tests for converting a transaction into quick/recurring/installment"""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            email="testuser@test.com", password="testpass123"
        )
        self.client.login(username="testuser@test.com", password="testpass123")

        self.currency = Currency.objects.create(
            code="USD", name="US Dollar", decimal_places=2, prefix="$ "
        )
        self.account = Account.objects.create(
            name="Test Account", currency=self.currency
        )
        self.category = TransactionCategory.objects.create(name="Test Category")
        self.tag = TransactionTag.objects.create(name="TestTag")

        self.transaction = Transaction.objects.create(
            account=self.account,
            type=Transaction.Type.EXPENSE,
            date=date(2030, 1, 15),
            amount=50,
            description="Gym",
            category=self.category,
            is_paid=True,
        )
        self.transaction.tags.add(self.tag)

    def _get(self, url_name):
        return self.client.get(
            reverse(url_name, kwargs={"transaction_id": self.transaction.id}),
            HTTP_HX_REQUEST="true",
        )

    def _post(self, url_name, data):
        return self.client.post(
            reverse(url_name, kwargs={"transaction_id": self.transaction.id}),
            data,
            HTTP_HX_REQUEST="true",
        )

    def test_quick_transaction_form_is_prefilled_without_name(self):
        response = self._get("transaction_convert_to_quick_transaction")
        self.assertEqual(response.status_code, 200)
        initial = response.context["form"].initial
        self.assertEqual(initial["description"], "Gym")
        self.assertEqual(initial["tags"], ["TestTag"])
        self.assertNotIn("name", initial)

    def test_quick_transaction_requires_name_and_keeps_transaction(self):
        data = {
            "account": self.account.id,
            "type": "EX",
            "amount": "50",
            "description": "Gym",
        }
        response = self._post("transaction_convert_to_quick_transaction", data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(QuickTransaction.objects.exists())

        response = self._post(
            "transaction_convert_to_quick_transaction", {**data, "name": "Gym"}
        )
        self.assertEqual(response.status_code, 204)
        self.assertTrue(QuickTransaction.objects.filter(name="Gym").exists())
        self.assertTrue(Transaction.objects.filter(id=self.transaction.id).exists())

    def test_recurring_transaction_adopts_original_as_first_occurrence(self):
        response = self._post(
            "transaction_convert_to_recurring_transaction",
            {
                "account": self.account.id,
                "type": "EX",
                "amount": "60",
                "description": "Gym",
                "category": self.category.id,
                "tags": ["TestTag"],
                "start_date": "2030-01-15",
                "recurrence_type": "month",
                "recurrence_interval": 1,
                "keep_at_most": 6,
            },
        )
        self.assertEqual(response.status_code, 204)

        recurring = RecurringTransaction.all_objects.get()
        self.transaction.refresh_from_db()
        self.assertEqual(self.transaction.recurring_transaction, recurring)
        # Paid amount is preserved
        self.assertEqual(self.transaction.amount, 50)
        self.assertEqual(
            recurring.transactions.filter(date=date(2030, 1, 15)).count(), 1
        )
        self.assertEqual(recurring.last_generated_date, date(2030, 1, 15))

    def test_installment_plan_adopts_original_as_first_installment(self):
        response = self._post(
            "transaction_convert_to_installment_plan",
            {
                "account": self.account.id,
                "type": "EX",
                "installment_amount": "50",
                "description": "TV",
                "add_description_to_transaction": "on",
                "number_of_installments": 3,
                "installment_start": 1,
                "start_date": "2030-01-15",
                "recurrence": "monthly",
            },
        )
        self.assertEqual(response.status_code, 204)

        plan = InstallmentPlan.all_objects.get()
        self.transaction.refresh_from_db()
        self.assertEqual(self.transaction.installment_plan, plan)
        self.assertEqual(self.transaction.installment_id, 1)
        self.assertTrue(self.transaction.is_paid)
        self.assertEqual(self.transaction.description, "TV")
        self.assertEqual(plan.transactions.count(), 3)

    def test_linked_transaction_cannot_be_converted_into_plan(self):
        self._post(
            "transaction_convert_to_installment_plan",
            {
                "account": self.account.id,
                "type": "EX",
                "installment_amount": "50",
                "description": "TV",
                "number_of_installments": 2,
                "installment_start": 1,
                "start_date": "2030-01-15",
                "recurrence": "monthly",
            },
        )
        self.assertEqual(
            self._get("transaction_convert_to_recurring_transaction").status_code, 404
        )
        self.assertEqual(
            self._get("transaction_convert_to_installment_plan").status_code, 404
        )
