from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Account, AccountGroup
from apps.currencies.models import Currency
from apps.transactions.models import (
    InstallmentPlan,
    QuickTransaction,
    RecurringTransaction,
    SubTransaction,
    Transaction,
)
from apps.transactions.filters import content_filter, exclude_matching
from apps.transactions.views.actions import clone_transaction


def _subs(*rows, initial=0):
    data = {"sub-TOTAL_FORMS": str(len(rows)), "sub-INITIAL_FORMS": str(initial)}
    for i, row in enumerate(rows):
        data.update({f"sub-{i}-{k}": v for k, v in row.items()})
    return data


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
    WHITENOISE_AUTOREFRESH=True,
)
class SubTransactionTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(email="u@test.com", password="pw")
        self.client.login(username="u@test.com", password="pw")
        currency = Currency.objects.create(code="USD", name="USD", decimal_places=2)
        self.account = Account.objects.create(
            name="A", group=AccountGroup.objects.create(name="G"), currency=currency
        )
        self.base = {
            "account": self.account.id,
            "type": "EX",
            "is_paid": True,
            "date": timezone.localdate().isoformat(),
            "description": "Groceries",
        }

    def _add(self, data):
        return self.client.post(
            reverse("transaction_add"), {**data, "submit": ""}, headers={"HX-Request": "true"}
        )

    def test_amount_is_sum_of_sub_transactions(self):
        response = self._add(
            {**self.base, "amount": "999", **_subs(
                {"name": "Milk", "amount": "2.50"}, {"name": "Bread", "amount": "4"}
            )}
        )
        self.assertEqual(response.status_code, 204)
        transaction = Transaction.objects.get()
        self.assertEqual(transaction.amount, Decimal("6.50"))
        self.assertEqual(
            list(transaction.sub_transactions.values_list("name", flat=True)),
            ["Milk", "Bread"],
        )

    def test_amount_required_without_sub_transactions(self):
        response = self._add({**self.base, **_subs()})
        self.assertEqual(response.status_code, 200)
        self.assertIn("amount", response.context["form"].errors)
        self.assertFalse(Transaction.objects.exists())

    def test_sub_transaction_needs_name(self):
        response = self._add({**self.base, **_subs({"name": "", "amount": "3"})})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Transaction.objects.exists())

    def test_edit_removing_sub_transactions_restores_typed_amount(self):
        transaction = Transaction.objects.create(
            account=self.account, type="EX", date=timezone.localdate(), amount=5
        )
        sub = SubTransaction.objects.create(transaction=transaction, name="Fee", amount=5)
        response = self.client.post(
            reverse("transaction_edit", kwargs={"transaction_id": transaction.id}),
            {**self.base, "amount": "12", **_subs(
                {"id": sub.id, "name": "Fee", "amount": "5", "DELETE": "on"}, initial=1
            )},
            headers={"HX-Request": "true"},
        )
        self.assertEqual(response.status_code, 204)
        transaction.refresh_from_db()
        self.assertEqual(transaction.amount, Decimal("12"))
        self.assertFalse(transaction.sub_transactions.exists())

    @override_settings(ENABLE_SOFT_DELETE=True)
    def test_soft_delete_hides_and_hard_delete_removes_sub_transactions(self):
        transaction = Transaction.objects.create(
            account=self.account, type="EX", date=timezone.localdate(), amount=5
        )
        SubTransaction.objects.create(transaction=transaction, name="Fee", amount=5)
        url = reverse("transaction_delete", kwargs={"transaction_id": transaction.id})
        self.client.delete(url, headers={"HX-Request": "true"})
        # soft: sub-transactions stay with (and are hidden by) the deleted parent
        self.assertTrue(Transaction.deleted_objects.filter(pk=transaction.pk).exists())
        self.assertEqual(SubTransaction.objects.count(), 1)
        self.client.delete(url, headers={"HX-Request": "true"})
        self.assertFalse(SubTransaction.objects.exists())

    def test_clone_copies_sub_transactions(self):
        transaction = Transaction.objects.create(
            account=self.account, type="EX", date=timezone.localdate(), amount=5
        )
        SubTransaction.objects.create(transaction=transaction, name="Fee", amount=5)
        clone = clone_transaction(transaction)
        self.assertEqual(list(clone.sub_transactions.values_list("name", "amount")), [("Fee", Decimal("5"))])

    def test_content_filter_matches_sub_transaction_names(self):
        shop = Transaction.objects.create(
            account=self.account, type="EX", date=timezone.localdate(), amount=5, description="Shop"
        )
        SubTransaction.objects.create(transaction=shop, name="Milk", amount=2)
        SubTransaction.objects.create(transaction=shop, name="Oat milk", amount=3)
        other = Transaction.objects.create(
            account=self.account, type="EX", date=timezone.localdate(), amount=1, description="Bus"
        )
        everything = Transaction.all_objects.all()
        self.assertEqual(list(content_filter(everything, "description", "milk")), [shop])
        self.assertEqual(list(exclude_matching(content_filter)(everything, "x", "milk")), [other])

    def test_bulk_edit_leaves_amount_of_split_transactions(self):
        split = Transaction.objects.create(
            account=self.account, type="EX", date=timezone.localdate(), amount=5
        )
        SubTransaction.objects.create(transaction=split, name="Fee", amount=5)
        plain = Transaction.objects.create(
            account=self.account, type="EX", date=timezone.localdate(), amount=1
        )
        response = self.client.post(
            reverse("transactions_bulk_edit"),
            {"transactions": [split.id, plain.id], "amount": "50", "description": "Edited"},
            headers={"HX-Request": "true"},
        )
        self.assertEqual(response.status_code, 204)
        split.refresh_from_db()
        plain.refresh_from_db()
        self.assertEqual((split.amount, split.description), (Decimal("5"), "Edited"))
        self.assertEqual(plain.amount, Decimal("50"))

    def _post(self, url_name, data):
        return self.client.post(reverse(url_name), data, headers={"HX-Request": "true"})

    def _parts(self, transaction):
        return list(transaction.sub_transactions.values_list("name", "amount"))

    def test_quick_transaction_parts_are_copied_to_created_transaction(self):
        self._post(
            "quick_transaction_add",
            {**self.base, "name": "Lunch", **_subs({"name": "Meal", "amount": "20"}, {"name": "Tip", "amount": "2"})},
        )
        quick = QuickTransaction.objects.get()
        self.assertEqual(quick.amount, Decimal("22"))
        self.client.get(
            reverse("quick_transaction_add_as_transaction", kwargs={"quick_transaction_id": quick.id}),
            headers={"HX-Request": "true"},
        )
        transaction = Transaction.objects.get()
        self.assertEqual(transaction.amount, Decimal("22"))
        self.assertEqual(self._parts(transaction), [("Meal", Decimal("20")), ("Tip", Decimal("2"))])

    def test_quick_transfer_drops_parts(self):
        other = Account.objects.create(name="B", group=self.account.group, currency=self.account.currency)
        response = self._post(
            "quick_transaction_add",
            {**self.base, "type": "TR", "to_account": other.id, "amount": "5", "name": "Move",
             **_subs({"name": "Hidden", "amount": "9"})},
        )
        self.assertEqual(response.status_code, 204)
        quick = QuickTransaction.objects.get()
        self.assertEqual(quick.amount, Decimal("5"))
        self.assertFalse(quick.sub_transactions.exists())

    def test_recurring_parts_follow_generated_and_unpaid_transactions(self):
        self._post(
            "recurring_transaction_add",
            {**self.base, "start_date": timezone.localdate().isoformat(), "recurrence_type": "month",
             "recurrence_interval": 1, "keep_at_most": 2, **_subs({"name": "Plan", "amount": "10"})},
        )
        recurring = RecurringTransaction.all_objects.get()
        self.assertEqual(recurring.amount, Decimal("10"))
        generated = recurring.transactions.all()
        self.assertTrue(generated)
        for transaction in generated:
            self.assertEqual(self._parts(transaction), [("Plan", Decimal("10"))])

        sub = recurring.sub_transactions.get()
        self.client.post(
            reverse("recurring_transaction_edit", kwargs={"recurring_transaction_id": recurring.id}),
            {**self.base, "start_date": timezone.localdate().isoformat(), "recurrence_type": "month",
             "recurrence_interval": 1, "keep_at_most": 2,
             **_subs({"id": sub.id, "name": "Plan", "amount": "10"}, {"name": "Tax", "amount": "1"}, initial=1)},
            headers={"HX-Request": "true"},
        )
        for transaction in recurring.transactions.all():
            self.assertEqual(transaction.amount, Decimal("11"))
            self.assertEqual(len(self._parts(transaction)), 2)

    def test_installment_parts_are_copied_to_each_installment(self):
        self._post(
            "installment_plan_add",
            {**self.base, "number_of_installments": 2, "installment_start": 1,
             "start_date": timezone.localdate().isoformat(), "recurrence": "monthly",
             **_subs({"name": "Principal", "amount": "90"}, {"name": "Interest", "amount": "10"})},
        )
        plan = InstallmentPlan.all_objects.get()
        self.assertEqual(plan.installment_amount, Decimal("100"))
        self.assertEqual(plan.transactions.count(), 2)
        for transaction in plan.transactions.all():
            self.assertEqual(transaction.amount, Decimal("100"))
            self.assertEqual(len(self._parts(transaction)), 2)
