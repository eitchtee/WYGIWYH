from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Account
from apps.currencies.models import Currency
from apps.transactions.models import Transaction, TransactionCategory, TransactionTag


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
    WHITENOISE_AUTOREFRESH=True,
)
class ExcludeFilterTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="exclude@test.com", password="pass"
        )
        self.client.force_login(self.user)
        currency = Currency.objects.create(code="BRL", name="Real", decimal_places=2)
        self.account = Account.objects.create(name="Wallet", currency=currency)
        food = TransactionCategory.objects.create(name="Food")
        home = TransactionTag.objects.create(name="home")

        self.make("Groceries", category=food).tags.add(home)
        self.make("Restaurant", category=food, notes="with friends")
        self.make("Rent").tags.add(home)
        self.make("Gift")

    def make(self, description, **kwargs):
        today = timezone.localdate(timezone.now())
        return Transaction.objects.create(
            account=self.account,
            type=Transaction.Type.EXPENSE,
            date=today,
            reference_date=today.replace(day=1),
            amount=Decimal("10"),
            description=description,
            **kwargs,
        )

    def listed(self, params):
        response = self.client.get(
            reverse("transactions_all_list"), params, HTTP_HX_REQUEST="true"
        )
        self.assertEqual(response.status_code, 200)
        page = response.context["page_obj"]
        late = response.context["late_transactions"] or []
        return sorted(t.description for t in [*page, *late])

    def test_exclusions_join_with_inclusions(self):
        cases = [
            ({"exclude_category": ["Food"]}, ["Gift", "Rent"]),
            ({"exclude_category": ["uncategorized"]}, ["Groceries", "Restaurant"]),
            ({"exclude_tags": ["home"]}, ["Gift", "Restaurant"]),
            ({"exclude_tags": ["untagged"]}, ["Groceries", "Rent"]),
            ({"exclude_description": "friends"}, ["Gift", "Groceries", "Rent"]),
            ({"exclude_account": ["Wallet"]}, []),
            # positive and negative filters are applied together
            ({"category": ["Food"], "exclude_tags": ["home"]}, ["Restaurant"]),
        ]
        for params, expected in cases:
            self.assertEqual(self.listed(params), expected, params)
