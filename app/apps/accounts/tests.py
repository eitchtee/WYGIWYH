from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError


from apps.accounts.models import Account, AccountGroup
from apps.currencies.models import Currency

User = get_user_model()


class BaseAccountAppTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="accuser@example.com", password="password")
        self.other_user = User.objects.create_user(email="otheraccuser@example.com", password="password")
        self.client = Client()
        self.client.login(email="accuser@example.com", password="password")

        self.currency_usd = Currency.objects.create(code="USD", name="US Dollar", decimal_places=2, prefix="$")
        self.currency_eur = Currency.objects.create(code="EUR", name="Euro", decimal_places=2, prefix="€")


class AccountGroupModelTests(BaseAccountAppTest):
    def test_account_group_creation(self):
        group = AccountGroup.objects.create(name="My Savings", owner=self.user)
        self.assertEqual(str(group), "My Savings")
        self.assertEqual(group.owner, self.user)

    def test_account_group_unique_together_owner_name(self):
        AccountGroup.objects.create(name="Unique Group", owner=self.user)
        with self.assertRaises(Exception): # IntegrityError at DB level
            AccountGroup.objects.create(name="Unique Group", owner=self.user)


class AccountGroupViewTests(BaseAccountAppTest):
    def test_account_groups_list_view(self):
        AccountGroup.objects.create(name="Group 1", owner=self.user)
        AccountGroup.objects.create(name="Group 2 Public", visibility=AccountGroup.Visibility.PUBLIC)
        response = self.client.get(reverse("account_groups_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Group 1")
        self.assertContains(response, "Group 2 Public")

    def test_account_group_add_view(self):
        response = self.client.post(reverse("account_group_add"), {"name": "New Group from View"})
        self.assertEqual(response.status_code, 204) # HTMX success
        self.assertTrue(AccountGroup.objects.filter(name="New Group from View", owner=self.user).exists())

    def test_account_group_edit_view(self):
        group = AccountGroup.objects.create(name="Original Group Name", owner=self.user)
        response = self.client.post(reverse("account_group_edit", args=[group.id]), {"name": "Edited Group Name"})
        self.assertEqual(response.status_code, 204)
        group.refresh_from_db()
        self.assertEqual(group.name, "Edited Group Name")

    def test_account_group_delete_view(self):
        group = AccountGroup.objects.create(name="Group to Delete", owner=self.user)
        response = self.client.delete(reverse("account_group_delete", args=[group.id]))
        self.assertEqual(response.status_code, 204)
        self.assertFalse(AccountGroup.objects.filter(id=group.id).exists())

    def test_other_user_cannot_edit_account_group(self):
        group = AccountGroup.objects.create(name="User1s Group", owner=self.user)
        self.client.logout()
        self.client.login(email="otheraccuser@example.com", password="password")
        response = self.client.post(reverse("account_group_edit", args=[group.id]), {"name": "Attempted Edit"})
        self.assertEqual(response.status_code, 204) # View returns 204 with message
        group.refresh_from_db()
        self.assertEqual(group.name, "User1s Group") # Name should not change


class AccountModelTests(BaseAccountAppTest): # Renamed from AccountTests
    def setUp(self):
        super().setUp()
        self.account_group = AccountGroup.objects.create(name="Test Group", owner=self.user)

    def test_account_creation(self):
        """Test basic account creation"""
        account = Account.objects.create(
            name="Test Account",
            group=self.account_group,
            currency=self.currency_usd,
            owner=self.user,
            is_asset=False,
            is_archived=False,
        )
        self.assertEqual(str(account), "Test Account")
        self.assertEqual(account.group, self.account_group)
        self.assertEqual(account.currency, self.currency_usd)
        self.assertEqual(account.owner, self.user)
        self.assertFalse(account.is_asset)
        self.assertFalse(account.is_archived)

    def test_account_with_exchange_currency(self):
        """Test account creation with exchange currency"""
        account = Account.objects.create(
            name="Exchange Account",
            currency=self.currency_usd,
            exchange_currency=self.currency_eur,
            owner=self.user
        )
        self.assertEqual(account.exchange_currency, self.currency_eur)

    def test_account_clean_exchange_currency_same_as_currency(self):
        account = Account(
            name="Same Currency Account",
            currency=self.currency_usd,
            exchange_currency=self.currency_usd, # Same as main currency
            owner=self.user
        )
        with self.assertRaises(ValidationError) as context:
            account.full_clean()
        self.assertIn('exchange_currency', context.exception.message_dict)
        self.assertIn("Exchange currency cannot be the same as the account's main currency.", context.exception.message_dict['exchange_currency'])

    def test_account_unique_together_owner_name(self):
        Account.objects.create(name="Unique Account", owner=self.user, currency=self.currency_usd)
        with self.assertRaises(Exception): # IntegrityError at DB level
            Account.objects.create(name="Unique Account", owner=self.user, currency=self.currency_eur)


class AccountViewTests(BaseAccountAppTest):
    def setUp(self):
        super().setUp()
        self.account_group = AccountGroup.objects.create(name="View Test Group", owner=self.user)

    def test_accounts_list_view(self):
        Account.objects.create(name="Acc 1", currency=self.currency_usd, owner=self.user, group=self.account_group)
        Account.objects.create(name="Acc 2 Public", currency=self.currency_eur, visibility=Account.Visibility.PUBLIC)
        response = self.client.get(reverse("accounts_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Acc 1")
        self.assertContains(response, "Acc 2 Public")

    def test_account_add_view(self):
        data = {
            "name": "New Checking Account",
            "group": self.account_group.id,
            "currency": self.currency_usd.id,
            "is_asset": "on", # Checkbox data
            "is_archived": "", # Not checked
        }
        response = self.client.post(reverse("account_add"), data)
        self.assertEqual(response.status_code, 204) # HTMX success
        self.assertTrue(
            Account.objects.filter(name="New Checking Account", owner=self.user, is_asset=True, is_archived=False).exists()
        )

    def test_account_edit_view(self):
        account = Account.objects.create(
            name="Original Account Name", currency=self.currency_usd, owner=self.user, group=self.account_group
        )
        data = {
            "name": "Edited Account Name",
            "group": self.account_group.id,
            "currency": self.currency_usd.id,
            "is_asset": "", # Uncheck asset
            "is_archived": "on", # Check archived
        }
        response = self.client.post(reverse("account_edit", args=[account.id]), data)
        self.assertEqual(response.status_code, 204)
        account.refresh_from_db()
        self.assertEqual(account.name, "Edited Account Name")
        self.assertFalse(account.is_asset)
        self.assertTrue(account.is_archived)

    def test_account_delete_view(self):
        account = Account.objects.create(name="Account to Delete", currency=self.currency_usd, owner=self.user)
        response = self.client.delete(reverse("account_delete", args=[account.id]))
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Account.objects.filter(id=account.id).exists())

    def test_other_user_cannot_edit_account(self):
        account = Account.objects.create(name="User1s Account", currency=self.currency_usd, owner=self.user)
        self.client.logout()
        self.client.login(email="otheraccuser@example.com", password="password")
        data = {"name": "Attempted Edit by Other", "currency": self.currency_usd.id} # Need currency
        response = self.client.post(reverse("account_edit", args=[account.id]), data)
        self.assertEqual(response.status_code, 204) # View returns 204 with message
        account.refresh_from_db()
        self.assertEqual(account.name, "User1s Account")

    def test_account_sharing_and_take_ownership(self):
        # Create a public account by user1
        public_account = Account.objects.create(
            name="Public Account", currency=self.currency_usd, owner=self.user, visibility=Account.Visibility.PUBLIC
        )
        # Login as other_user
        self.client.logout()
        self.client.login(email="otheraccuser@example.com", password="password")

        # other_user takes ownership
        response = self.client.get(reverse("account_take_ownership", args=[public_account.id]))
        self.assertEqual(response.status_code, 204)
        public_account.refresh_from_db()
        self.assertEqual(public_account.owner, self.other_user)
        self.assertEqual(public_account.visibility, Account.Visibility.PRIVATE) # Should become private

        # Now, original user (self.user) should not be able to edit it
        self.client.logout()
        self.client.login(email="accuser@example.com", password="password")
        response = self.client.post(reverse("account_edit", args=[public_account.id]), {"name": "Attempt by Original Owner", "currency": self.currency_usd.id})
        self.assertEqual(response.status_code, 204) # error message, no change
        public_account.refresh_from_db()
        self.assertNotEqual(public_account.name, "Attempt by Original Owner")

    def test_account_share_view(self):
        account_to_share = Account.objects.create(name="Shareable Account", currency=self.currency_usd, owner=self.user)
        data = {
            "shared_with": [self.other_user.id],
            "visibility": Account.Visibility.SHARED,
        }
        response = self.client.post(reverse("account_share", args=[account_to_share.id]), data)
        self.assertEqual(response.status_code, 204)
        account_to_share.refresh_from_db()
        self.assertIn(self.other_user, account_to_share.shared_with.all())
        self.assertEqual(account_to_share.visibility, Account.Visibility.SHARED)
