from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.models import Account, InvestmentClass
from apps.currencies.models import Currency


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
    WHITENOISE_AUTOREFRESH=True,
    DEMO=False,
)
class InvestmentClassAPITests(TestCase):
    def setUp(self):
        User = get_user_model()
        perms = Permission.objects.filter(
            codename__in=[
                "add_investmentclass",
                "change_investmentclass",
                "delete_investmentclass",
                "change_account",
            ]
        )
        self.user = User.objects.create_user(email="u@test.com", password="pw")
        self.other = User.objects.create_user(email="o@test.com", password="pw")
        for user in (self.user, self.other):
            user.user_permissions.set(perms)
        self.api = APIClient()
        self.api.force_authenticate(User.objects.get(pk=self.user.pk))

    def test_crud_and_validation(self):
        response = self.api.post(
            "/api/investment-classes/", {"name": "Stocks", "target": "60"}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)
        stocks_id = response.data["id"]

        # Same name again, and targets past 100%: rejected, not a server error
        response = self.api.post("/api/investment-classes/", {"name": "Stocks"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("name", response.data)
        response = self.api.post(
            "/api/investment-classes/", {"name": "Bonds", "target": "50"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("target", response.data)

        # Editing keeps its own target out of the sum
        response = self.api.patch(
            f"/api/investment-classes/{stocks_id}/", {"target": "100"}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)

        # Another user's names and targets don't count, and they can't see ours
        other = APIClient()
        other.force_authenticate(get_user_model().objects.get(pk=self.other.pk))
        response = other.post(
            "/api/investment-classes/", {"name": "Stocks", "target": "100"}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(other.get(f"/api/investment-classes/{stocks_id}/").status_code, 404)

    def test_account_takes_a_class(self):
        brl = Currency.objects.create(code="BRL", name="Real", decimal_places=2)
        stocks = InvestmentClass.all_objects.create(name="Stocks", owner=self.user)
        account = Account.all_objects.create(name="PETR4", currency=brl, owner=self.user)

        response = self.api.patch(
            f"/api/accounts/{account.id}/", {"investment_class_id": stocks.id}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["investment_class"]["name"], "Stocks")
        response = self.api.get("/api/accounts/", {"investment_class": stocks.id})
        self.assertEqual(response.data["count"], 1)
