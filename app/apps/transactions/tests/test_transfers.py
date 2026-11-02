from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Account, AccountGroup
from apps.common.middleware.thread_local import delete_current_user, write_current_user
from apps.currencies.models import Currency
from apps.transactions.forms import RecurringTransactionForm, TransferForm
from apps.transactions.models import (
    QuickTransaction,
    RecurringTransaction,
    Transaction,
    TransactionCategory,
    TransactionTag,
)
from apps.rules.signals import transaction_created, transaction_updated
from apps.transactions.views.actions import clone_transaction


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
    WHITENOISE_AUTOREFRESH=True,
)
class TransferTestBase(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="transfer@test.com", password="testpass123"
        )
        self.client.login(username="transfer@test.com", password="testpass123")
        write_current_user(self.user)
        self.addCleanup(delete_current_user)
        currency = Currency.objects.create(code="USD", name="US Dollar", decimal_places=2)
        group = AccountGroup.objects.create(name="Group")
        self.checking = Account.objects.create(name="Checking", group=group, currency=currency)
        self.savings = Account.objects.create(name="Savings", group=group, currency=currency)

    def _transfer(self, **overrides):
        data = {
            "from_account": self.checking.id,
            "to_account": self.savings.id,
            "from_amount": "100",
            "to_amount": "98",
            "date": "2026-03-10",
            "reference_date": "2026-03-01",
            "description": "Move money",
            "mute": True,
            **overrides,
        }
        form = TransferForm(data)
        self.assertTrue(form.is_valid(), form.errors)
        return form.save()


class TransferTests(TransferTestBase):
    def test_creates_linked_pair_with_own_amounts(self):
        from_t, to_t = self._transfer()
        from_t.refresh_from_db()
        to_t.refresh_from_db()

        self.assertEqual(from_t.linked_transaction, to_t)
        self.assertEqual(to_t.linked_transaction, from_t)
        self.assertEqual(from_t.type, Transaction.Type.EXPENSE)
        self.assertEqual(to_t.type, Transaction.Type.INCOME)
        self.assertEqual(from_t.amount, Decimal("100"))
        self.assertEqual(to_t.amount, Decimal("98"))

    def test_listing_collapses_pair_unless_one_side_is_filtered_out(self):
        from_t, to_t = self._transfer()
        Transaction.objects.create(
            account=self.checking, type="IN", date=date(2026, 3, 1), amount=5
        )

        listed = Transaction.objects.all().collapse_transfers()
        self.assertEqual(listed.count(), 2)
        self.assertNotIn(to_t, listed)

        only_savings = Transaction.objects.filter(account=self.savings)
        self.assertEqual(list(only_savings.collapse_transfers()), [to_t])

    def test_shared_fields_stay_in_sync(self):
        from_t, to_t = self._transfer()

        to_t.date = date(2026, 4, 2)
        to_t.reference_date = date(2026, 4, 1)
        to_t.is_paid = False
        to_t.save()

        from_t.refresh_from_db()
        self.assertEqual(from_t.date, date(2026, 4, 2))
        self.assertEqual(from_t.reference_date, date(2026, 4, 1))
        self.assertFalse(from_t.is_paid)

    def test_edit_updates_both_sides(self):
        from_t, to_t = self._transfer()

        form = TransferForm(
            {
                "from_account": self.checking.id,
                "to_account": self.savings.id,
                "from_amount": "50",
                "to_amount": "49",
                "date": "2026-03-15",
                "description": "Edited",
            },
            instance=to_t,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        self.assertEqual(Transaction.objects.count(), 2)
        from_t.refresh_from_db()
        to_t.refresh_from_db()
        self.assertEqual((from_t.amount, to_t.amount), (Decimal("50"), Decimal("49")))
        self.assertEqual(from_t.date, to_t.date)
        self.assertEqual(to_t.description, "Edited")

    @override_settings(ENABLE_SOFT_DELETE=True)
    def test_delete_and_restore_both_sides(self):
        from_t, to_t = self._transfer()

        from_t.delete()
        self.assertEqual(Transaction.objects.count(), 0)

        response = self.client.get(
            reverse("transaction_undelete", kwargs={"transaction_id": to_t.id}),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(Transaction.objects.count(), 2)

    @override_settings(ENABLE_SOFT_DELETE=False)
    def test_hard_delete_both_sides(self):
        from_t, _ = self._transfer()
        from_t.delete()
        self.assertEqual(Transaction.userless_all_objects.count(), 0)

    def test_clone_creates_new_linked_pair(self):
        from_t, to_t = self._transfer()

        new_from = clone_transaction(from_t)
        new_to = new_from.linked_transaction

        self.assertEqual(Transaction.objects.count(), 4)
        self.assertEqual(new_to.linked_transaction, new_from)
        self.assertEqual(new_to.amount, to_t.amount)

    def test_edit_view_routes_transfer_to_transfer_form(self):
        _, to_t = self._transfer()

        response = self.client.get(
            reverse("transaction_edit", kwargs={"transaction_id": to_t.id}),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.context["form"], TransferForm)

    def test_monthly_list_renders_transfer_once(self):
        from_t, to_t = self._transfer()

        response = self.client.get(
            reverse("monthly_transactions_list", kwargs={"month": 3, "year": 2026}),
            HTTP_HX_REQUEST="true",
        )
        content = response.content.decode()
        self.assertIn(f'data-transaction-id="{from_t.id}"', content)
        self.assertNotIn(f'data-transaction-id="{to_t.id}"', content)
        self.assertIn("Savings", content)

    def test_combine_transfers_off_lists_both_sides(self):
        self.user.settings.combine_transfers = False
        self.user.settings.save()
        from_t, to_t = self._transfer()

        self.assertEqual(Transaction.objects.all().collapse_transfers().count(), 2)
        response = self.client.get(
            reverse("monthly_transactions_list", kwargs={"month": 3, "year": 2026}),
            HTTP_HX_REQUEST="true",
        )
        content = response.content.decode()
        self.assertIn(f'data-transaction-id="{from_t.id}"', content)
        self.assertIn(f'data-transaction-id="{to_t.id}"', content)
        self.assertEqual(content.count("fa-right-left"), 2)  # marker on each side

    def test_item_shows_both_sides_category_and_tags(self):
        out_cat = TransactionCategory.objects.create(name="OutCat")
        in_cat = TransactionCategory.objects.create(name="InCat")
        out_tag = TransactionTag.objects.create(name="OutTag")
        in_tag = TransactionTag.objects.create(name="InTag")
        self._transfer(
            from_category=str(out_cat.id),
            to_category=str(in_cat.id),
            from_tags=[out_tag.name],
            to_tags=[in_tag.name],
        )

        response = self.client.get(
            reverse("monthly_transactions_list", kwargs={"month": 3, "year": 2026}),
            HTTP_HX_REQUEST="true",
        )
        content = response.content.decode()
        for name in ("OutCat", "InCat", "OutTag", "InTag"):
            self.assertIn(name, content)


class TransferTemplateTests(TransferTestBase):
    """Recurring and quick transactions of type Transfer."""

    def _recurring(self, **overrides):
        return RecurringTransaction.objects.create(
            account=self.checking,
            type=RecurringTransaction.Type.TRANSFER,
            to_account=self.savings,
            amount=Decimal("100"),
            to_amount=Decimal("95"),
            description="Savings",
            start_date=timezone.localdate(),
            recurrence_type=RecurringTransaction.RecurrenceType.MONTH,
            recurrence_interval=1,
            keep_at_most=2,
            **overrides,
        )

    def test_recurring_transfer_generates_linked_pairs(self):
        recurring = self._recurring()
        recurring.create_upcoming_transactions()

        sides = recurring.transactions.all()
        expenses = sides.filter(type=Transaction.Type.EXPENSE)
        self.assertEqual(sides.count(), expenses.count() * 2)
        for from_t in expenses:
            to_t = from_t.linked_transaction
            self.assertEqual(to_t.linked_transaction, from_t)
            self.assertEqual(to_t.account, self.savings)
            self.assertEqual(to_t.amount, Decimal("95"))
            self.assertEqual(to_t.recurring_transaction, recurring)
            self.assertEqual(to_t.date, from_t.date)

    def test_recurring_update_keeps_side_amounts(self):
        recurring = self._recurring()
        recurring.create_upcoming_transactions()

        recurring.amount, recurring.to_amount = Decimal("10"), Decimal("9")
        recurring.save()
        recurring.update_unpaid_transactions()

        amounts = set(recurring.transactions.values_list("type", "amount"))
        self.assertEqual(
            amounts,
            {(Transaction.Type.EXPENSE, Decimal("10")), (Transaction.Type.INCOME, Decimal("9"))},
        )

    def test_transfer_type_requires_other_account(self):
        form = RecurringTransactionForm(
            {
                "type": "TR",
                "account": self.checking.id,
                "amount": "10",
                "description": "x",
                "start_date": "2026-03-01",
                "recurrence_type": "month",
                "recurrence_interval": "1",
                "keep_at_most": "2",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("to_account", form.errors)

    def test_quick_transfer_creates_linked_pair(self):
        quick = QuickTransaction.objects.create(
            name="To savings",
            account=self.checking,
            type=QuickTransaction.Type.TRANSFER,
            to_account=self.savings,
            amount=Decimal("20"),
        )

        response = self.client.get(
            reverse(
                "quick_transaction_add_as_transaction",
                kwargs={"quick_transaction_id": quick.id},
            ),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 204)
        from_t = Transaction.objects.get(type=Transaction.Type.EXPENSE)
        self.assertEqual(from_t.account, self.checking)
        self.assertEqual(from_t.linked_transaction.account, self.savings)
        self.assertEqual(from_t.linked_transaction.amount, Decimal("20"))

    def test_convert_transfer_to_recurring_adopts_both_sides(self):
        from_t, to_t = self._transfer()

        response = self.client.post(
            reverse(
                "transaction_convert_to_recurring_transaction",
                kwargs={"transaction_id": to_t.id},
            ),
            {
                "type": "TR",
                "account": self.checking.id,
                "to_account": self.savings.id,
                "amount": "100",
                "to_amount": "98",
                "description": "Move money",
                "add_description_to_transaction": "on",
                "start_date": "2026-03-10",
                "recurrence_type": "month",
                "recurrence_interval": "1",
                "keep_at_most": "1",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 204)
        from_t.refresh_from_db()
        to_t.refresh_from_db()
        self.assertIsNotNone(from_t.recurring_transaction)
        self.assertEqual(to_t.recurring_transaction, from_t.recurring_transaction)
        self.assertEqual(from_t.linked_transaction, to_t)


class TransferRuleSignalTests(TransferTestBase):
    def _capture(self, signal):
        senders = []

        def receiver(sender, **kwargs):
            senders.append((sender.pk, kwargs.get("old_data")))

        signal.connect(receiver, weak=False)
        self.addCleanup(signal.disconnect, receiver)
        return senders

    def test_create_and_edit_trigger_rules_for_both_sides(self):
        created = self._capture(transaction_created)
        from_t, to_t = self._transfer()
        self.assertEqual({pk for pk, _ in created}, {from_t.pk, to_t.pk})

        updated = self._capture(transaction_updated)
        form = TransferForm(
            {
                "from_account": self.checking.id,
                "to_account": self.savings.id,
                "from_amount": "7",
                "date": "2026-04-10",  # date change used to fire "updated" twice for the "to" side
            },
            instance=from_t,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        self.assertEqual(sorted(pk for pk, _ in updated), sorted([from_t.pk, to_t.pk]))
        old_amounts = {old.amount for _, old in updated}
        self.assertEqual(old_amounts, {Decimal("100"), Decimal("98")})


class TransferReviewFixTests(TransferTestBase):
    def test_pair_of_two_incomes_stays_listed(self):
        from_t, to_t = self._transfer()
        Transaction.objects.filter(pk=from_t.pk).update(type=Transaction.Type.INCOME)

        listed = Transaction.objects.all().collapse_transfers()
        self.assertEqual(listed.count(), 2)

    @override_settings(ENABLE_SOFT_DELETE=False)
    def test_bulk_delete_removes_both_sides(self):
        from_t, _ = self._transfer()

        response = self.client.get(
            reverse("transactions_bulk_delete") + f"?transactions={from_t.id}",
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(Transaction.userless_all_objects.count(), 0)

    @override_settings(ENABLE_SOFT_DELETE=False)
    def test_delete_leaves_a_side_the_user_cannot_see(self):
        other = get_user_model().objects.create_user(
            email="other@test.com", password="testpass123"
        )
        hidden = Account.objects.create(
            name="Hidden",
            currency=self.checking.currency,
            owner=other,
            visibility="private",
        )
        from_t = Transaction.objects.create(
            account=self.checking, type="EX", date=date(2026, 3, 1), amount=5
        )
        partner = from_t.add_transfer_side(hidden, Decimal("5"))

        from_t.delete()

        partner.refresh_from_db()
        self.assertIsNone(partner.linked_transaction)
