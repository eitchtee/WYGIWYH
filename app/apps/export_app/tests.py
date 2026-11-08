import io
import zipfile
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.models import Account, InvestmentClass
from apps.common.middleware.thread_local import delete_current_user, write_current_user
from apps.currencies.models import Currency
from apps.export_app.resources.accounts import AccountResource, InvestmentClassResource
from apps.export_app.resources.transactions import TransactionEntityResource
from apps.export_app.views import process_imports
from apps.transactions.models import TransactionEntity


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
