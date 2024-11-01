from django.test import TestCase

from apps.accounts.models import Account, AccountGroup
from apps.currencies.models import Currency


class AccountTests(TestCase):
    def setUp(self):
        """Set up test data"""
        self.currency = Currency.objects.create(
            code="USD", name="US Dollar", decimal_places=2, prefix="$ "
        )
        self.exchange_currency = Currency.objects.create(
            code="EUR", name="Euro", decimal_places=2, prefix="€ "
        )
        self.account_group = AccountGroup.objects.create(name="Test Group")

    def test_account_creation(self):
        """Test basic account creation"""
        account = Account.objects.create(
            name="Test Account",
            group=self.account_group,
            currency=self.currency,
            is_asset=False,
            is_archived=False,
        )
        self.assertEqual(str(account), "Test Account")
        self.assertEqual(account.name, "Test Account")
        self.assertEqual(account.group, self.account_group)
        self.assertEqual(account.currency, self.currency)
        self.assertFalse(account.is_asset)
        self.assertFalse(account.is_archived)

    def test_account_with_exchange_currency(self):
        """Test account creation with exchange currency"""
        account = Account.objects.create(
            name="Exchange Account",
            currency=self.currency,
            exchange_currency=self.exchange_currency,
        )
        self.assertEqual(account.exchange_currency, self.exchange_currency)
