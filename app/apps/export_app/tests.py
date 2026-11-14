import io
from datetime import date
import zipfile
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.models import Account, InvestmentClass
from apps.common.middleware.thread_local import delete_current_user, write_current_user
from apps.currencies.models import Currency
from apps.export_app.resources.accounts import AccountResource, InvestmentClassResource
from apps.export_app.resources.transactions import (
    InstallmentPlanResource,
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
    TransactionEntity,
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
