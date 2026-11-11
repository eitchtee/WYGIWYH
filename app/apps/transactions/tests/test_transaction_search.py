from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Account
from apps.currencies.models import Currency
from apps.transactions.models import (
    Transaction,
    TransactionCategory,
    TransactionEntity,
    TransactionTag,
)


class TransactionSearchTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="search@test.com", password="pass"
        )
        self.client.login(username="search@test.com", password="pass")
        self.user.settings.date_format = "d/m/Y"
        self.user.settings.number_format = "DC"
        self.user.settings.save()

        currency = Currency.objects.create(code="BRL", name="Real", decimal_places=2)
        self.account = Account.objects.create(name="Wallet", currency=currency)
        self.today = timezone.localdate(timezone.now())

    def make(self, days, description="", amount="10", **kwargs):
        return Transaction.objects.create(
            account=kwargs.pop("account", self.account),
            type=Transaction.Type.EXPENSE,
            date=self.today + timedelta(days=days),
            reference_date=(self.today + timedelta(days=days)).replace(day=1),
            amount=Decimal(amount),
            description=description,
            **kwargs,
        )

    def search(self, q=""):
        response = self.client.get(reverse("transactions_search"), {"q": q})
        self.assertEqual(response.status_code, 200)
        return [row["description"] for row in response.json()]

    def test_order_matches_monthly_view(self):
        for days, name in [(-30, "old"), (-2, "recent"), (-1, "yesterday"),
                           (10, "far"), (2, "soon"), (1, "tomorrow"), (0, "today")]:
            self.make(days, name)
        self.assertEqual(
            self.search(),
            ["today", "tomorrow", "yesterday", "soon", "far", "recent", "old"],
        )

    def test_search_fields(self):
        t = self.make(-5, "Groceries", amount="1234.56")
        t.category = TransactionCategory.objects.create(name="Food")
        t.save()
        t.tags.add(TransactionTag.objects.create(name="home"),
                   TransactionTag.objects.create(name="weekly"))
        t.entities.add(TransactionEntity.objects.create(name="Market"))
        self.make(-6, "Other", amount="5")

        day = (self.today - timedelta(days=5))
        for q in ["food", "market", "1.234,56", "1234",
                  day.strftime("%d/%m/%Y"), day.strftime("%d/%m"),
                  "home weekly", "groceries food"]:
            self.assertEqual(self.search(q), ["Groceries"], q)

        self.assertEqual(self.search("wallet"), ["Groceries", "Other"])
        self.assertEqual(self.search("groceries nomatch"), [])

    def test_filters_by_currency(self):
        usd = Currency.objects.create(code="USD", name="Dollar", decimal_places=2)
        other = Account.objects.create(name="Bank", currency=usd)
        self.make(0, "brl")
        self.make(0, "usd", account=other)
        response = self.client.get(
            reverse("transactions_search"), {"q": "", "currency": usd.id}
        )
        self.assertEqual([r["description"] for r in response.json()], ["usd"])
