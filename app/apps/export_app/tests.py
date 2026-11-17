import io
from datetime import date
import zipfile
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from django.test.utils import CaptureQueriesContext

from apps.accounts.models import Account, InvestmentClass
from apps.common.middleware.thread_local import delete_current_user, write_current_user
from apps.currencies.models import Currency
from apps.export_app.resources.accounts import AccountResource, InvestmentClassResource
from apps.export_app.resources.transactions import (
    InstallmentPlanResource,
    RecurringTransactionResource,
    TransactionCategoyResource,
    TransactionTagResource,
    QuickTransactionResource,
    SubTransactionResource,
    TransactionEntityResource,
    TransactionResource,
)
from apps.export_app.views import process_imports
from apps.transactions.models import (
    InstallmentPlan,
    QuickTransaction,
    SubTransaction,
    Transaction,
    TransactionCategory,
    TransactionEntity,
    TransactionTag,
)


class InvestmentRestoreTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(email="u@test.com", password="pw")
        write_current_user(self.user)

    def tearDown(self):
        delete_current_user()

    def test_round_trip_keeps_asset_class_and_income_links(self):
        brl = Currency.objects.create(code="BRL", name="Real", decimal_places=2)
        stocks = InvestmentClass.objects.create(name="Stocks", target=Decimal("60"))
        broker = TransactionEntity.objects.create(name="Broker")
        account = Account.objects.create(
            name="PETR4", currency=brl, is_investment=True, investment_class=stocks
        )
        account.income_entities.add(broker)

        backup = io.BytesIO()
        with zipfile.ZipFile(backup, "w") as z:
            for resource, name in (
                (AccountResource, "accounts"),
                (InvestmentClassResource, "investment_classes"),
                (TransactionEntityResource, "transactions_entities"),
            ):
                z.writestr(f"{name}.csv", resource().export().csv)

        Account.all_objects.all().delete()
        InvestmentClass.all_objects.all().delete()
        TransactionEntity.all_objects.all().delete()

        backup.seek(0)
        process_imports(None, {"zip_file": backup})

        account = Account.all_objects.get(name="PETR4")
        self.assertEqual(account.investment_class.name, "Stocks")
        self.assertEqual(account.investment_class.target, Decimal("60"))
        self.assertEqual([e.name for e in account.income_entities.all()], ["Broker"])


class SubTransactionBackupTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(email="s@test.com", password="pw")
        write_current_user(self.user)
        self.addCleanup(delete_current_user)
        account = Account.objects.create(
            name="A", currency=Currency.objects.create(code="USD", name="USD", decimal_places=2)
        )
        self.transaction = Transaction.objects.create(
            account=account, type="EX", date=date(2030, 1, 10), amount=5
        )
        self.plan = InstallmentPlan.objects.create(
            account=account, type="EX", description="Laptop", number_of_installments=2,
            start_date=date(2030, 1, 10), installment_amount=100,
        )
        SubTransaction.objects.create(transaction=self.transaction, name="Fee", amount="1.25")
        SubTransaction.objects.create(transaction=self.transaction, name="Item", amount="3.75")
        SubTransaction.objects.create(installment_plan=self.plan, name="Principal", amount=100)
        lunch = QuickTransaction.objects.create(
            name="Lunch", account=account, type="EX", amount=Decimal("13.90")
        )
        SubTransaction.objects.create(quick_transaction=lunch, name="Meal", amount="11.90")
        SubTransaction.objects.create(quick_transaction=lunch, name="Tip", amount=2)

    def _parts(self):
        return sorted(
            SubTransaction.objects.values_list(
                "name", "transaction", "installment_plan", "quick_transaction__name", "amount"
            )
        )

    def test_round_trip_puts_parts_back_on_their_parents(self):
        before = self._parts()
        backup = io.BytesIO()
        with zipfile.ZipFile(backup, "w") as z:
            for resource, name in (
                (TransactionResource(), "transactions"),
                (InstallmentPlanResource(), "installment_plans"),
                (QuickTransactionResource(), "quick_transactions"),
                (SubTransactionResource(), "sub_transactions"),
            ):
                z.writestr(f"{name}.csv", resource.export().csv)

        SubTransaction.objects.all().delete()
        QuickTransaction.all_objects.all().delete()
        backup.seek(0)
        process_imports(None, {"zip_file": backup})

        self.assertEqual(self._parts(), before)

    def test_exports_only_the_parts_of_exported_parents(self):
        dataset = SubTransactionResource(parents=["installment_plan"]).export()
        self.assertEqual([row["name"] for row in dataset.dict], ["Principal"])


class MultiUserRestoreTests(TestCase):
    """Export and restore run as the admin; other users' private names must survive (#691)."""

    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser(email="admin@x.com", password="pw")
        self.bob = User.objects.create_user(email="bob@x.com", password="pw")
        usd = Currency.objects.create(code="USD", name="USD", decimal_places=2)
        for user in (self.admin, self.bob):
            write_current_user(user)
            account = Account.objects.create(name="Checking", currency=usd)
            food = TransactionCategory.objects.create(name="Food")
            transaction = Transaction.objects.create(
                account=account, type="EX", date=date(2030, 1, 1), amount=1,
                category=food, description="lunch",
            )
            transaction.tags.add(TransactionTag.objects.create(name="groceries"))
            InstallmentPlan.objects.create(
                account=account, type="EX", description="TV", number_of_installments=1,
                start_date=date(2030, 1, 1), installment_amount=10, category=food,
            )
        write_current_user(self.admin)
        self.addCleanup(delete_current_user)

    def _state(self):
        return sorted(
            (t.account.owner.email, t.category.owner.email, [g.owner.email for g in t.tags(manager="all_objects").all()])
            for t in Transaction.userless_all_objects.all()
        ) + sorted(
            (p.account.owner.email, p.category.owner.email)
            for p in InstallmentPlan.all_objects.all()
        )

    def test_round_trip_keeps_each_users_categories_and_tags(self):
        before = self._state()
        backup = io.BytesIO()
        with zipfile.ZipFile(backup, "w") as z:
            for resource, name in (
                (TransactionCategoyResource(), "transactions_categories"),
                (TransactionTagResource(), "transactions_tags"),
                (TransactionResource(), "transactions"),
                (InstallmentPlanResource(), "installment_plans"),
            ):
                z.writestr(f"{name}.csv", resource.export().csv)

        Transaction.userless_all_objects.all().delete()
        InstallmentPlan.all_objects.all().delete()
        TransactionCategory.all_objects.all().delete()
        TransactionTag.all_objects.all().delete()
        backup.seek(0)
        process_imports(None, {"zip_file": backup})

        self.assertEqual(self._state(), before)

    def test_missing_names_are_created_for_the_rows_owner(self):
        csv = TransactionResource().export().csv
        Transaction.userless_all_objects.all().delete()
        InstallmentPlan.all_objects.all().delete()
        TransactionCategory.all_objects.all().delete()
        TransactionTag.all_objects.all().delete()

        process_imports(None, {"transactions": io.BytesIO(csv.encode())})

        self.assertEqual(
            sorted(TransactionCategory.all_objects.values_list("owner__email", flat=True)),
            ["admin@x.com", "bob@x.com"],
        )
        self.assertEqual(
            sorted(TransactionTag.all_objects.values_list("owner__email", flat=True)),
            ["admin@x.com", "bob@x.com"],
        )

    def test_export_queries_do_not_grow_with_rows(self):
        # A few queries per row timed big exports out (#692)
        def export_queries():
            with CaptureQueriesContext(connection) as queries:
                TransactionResource().export()
            return len(queries)

        few = export_queries()
        template = Transaction.userless_all_objects.first()
        for _ in range(5):
            copy = Transaction.all_objects.create(
                account=template.account, type="EX", date=date(2030, 1, 2), amount=1,
                category=template.category, owner=template.owner,
            )
            copy.tags.set(template.tags(manager="all_objects").all())

        self.assertEqual(export_queries(), few)


class ExportViewTests(TestCase):
    def setUp(self):
        self.client.force_login(
            get_user_model().objects.create_superuser(email="a@test.com", password="pw")
        )

    def test_nothing_selected_warns_instead_of_downloading(self):
        response = self.client.post(reverse("export_form"), {}, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(
            [m.level_tag for m in get_messages(response.wsgi_request)], ["warning"]
        )

    def test_non_superuser_is_refused_not_sent_back_to_login(self):
        # The login page sends signed-in users back to ?next=, so redirecting there looped
        self.client.force_login(
            get_user_model().objects.create_user(email="b@test.com", password="pw")
        )
        self.assertEqual(self.client.get(reverse("export_index")).status_code, 403)

    def test_restore_without_files_shows_the_error_in_the_form(self):
        response = self.client.post(reverse("restore_form"), {}, HTTP_HX_REQUEST="true")
        self.assertContains(response, "Please upload either a ZIP file or at least one CSV file")
        self.assertContains(response, 'id="restore-form"')
