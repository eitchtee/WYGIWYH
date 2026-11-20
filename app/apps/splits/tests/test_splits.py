from decimal import Decimal
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Account
from apps.currencies.models import Currency
from apps.splits.models import (
    SplitAttachment,
    SplitEvent,
    SplitExpense,
    SplitExpenseShare,
    SplitParticipant,
    SplitPayment,
    SplitTransactionLink,
)
from apps.splits.services.settlement import (
    ParticipantBalance,
    calculate_event_balances,
    get_event_settlement_summary,
    simplify_debts,
)
from apps.splits.services.splitting import compute_expense_shares
from apps.transactions.models import Transaction

User = get_user_model()


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
)
class SplitTestBase(TestCase):
    def setUp(self):
        self.currency = Currency.objects.create(
            code="USD", name="US Dollar", decimal_places=2, prefix="$"
        )
        self.creator = User.objects.create_user(
            email="creator@example.com",
            password="password123",
            first_name="Alice",
            last_name="Creator",
        )
        self.other_user = User.objects.create_user(
            email="bob@example.com",
            password="password123",
            first_name="Bob",
            last_name="Member",
        )
        self.account = Account.objects.create(
            owner=self.creator,
            name="Checking",
            currency=self.currency,
        )
        self.event = SplitEvent.objects.create(
            name="Beach Trip",
            currency=self.currency,
            creator=self.creator,
        )
        self.p_alice = SplitParticipant.objects.create(
            event=self.event,
            user=self.creator,
            name="Alice Creator",
            is_external=False,
        )
        self.p_bob = SplitParticipant.objects.create(
            event=self.event,
            user=self.other_user,
            name="Bob Member",
            is_external=False,
        )
        self.p_charlie = SplitParticipant.objects.create(
            event=self.event,
            user=None,
            name="Charlie",
            is_external=True,
        )


class SplittingAlgorithmTests(SplitTestBase):
    def test_equal_split_distributes_remainder_pennies(self):
        shares = compute_expense_shares(
            total_amount=Decimal("10.00"),
            split_type=SplitExpense.SplitType.EQUAL,
            participants=[self.p_alice, self.p_bob, self.p_charlie],
            decimal_places=2,
        )
        amounts = [s.amount for s in shares]
        self.assertEqual(sum(amounts), Decimal("10.00"))
        self.assertEqual(sorted(amounts), [Decimal("3.33"), Decimal("3.33"), Decimal("3.34")])

    def test_exact_split_valid_and_invalid(self):
        shares = compute_expense_shares(
            total_amount=Decimal("100.00"),
            split_type=SplitExpense.SplitType.EXACT,
            participants=[self.p_alice, self.p_bob],
            decimal_places=2,
            values_by_participant_id={
                self.p_alice.id: Decimal("30.00"),
                self.p_bob.id: Decimal("70.00"),
            },
        )
        self.assertEqual([s.amount for s in shares], [Decimal("30.00"), Decimal("70.00")])

        with self.assertRaises(ValidationError):
            compute_expense_shares(
                total_amount=Decimal("100.00"),
                split_type=SplitExpense.SplitType.EXACT,
                participants=[self.p_alice, self.p_bob],
                decimal_places=2,
                values_by_participant_id={
                    self.p_alice.id: Decimal("30.00"),
                    self.p_bob.id: Decimal("60.00"),
                },
            )

    def test_percentage_split_valid_and_invalid(self):
        shares = compute_expense_shares(
            total_amount=Decimal("200.00"),
            split_type=SplitExpense.SplitType.PERCENTAGE,
            participants=[self.p_alice, self.p_bob],
            decimal_places=2,
            values_by_participant_id={
                self.p_alice.id: Decimal("25"),
                self.p_bob.id: Decimal("75"),
            },
        )
        self.assertEqual([s.amount for s in shares], [Decimal("50.00"), Decimal("150.00")])

        with self.assertRaises(ValidationError):
            compute_expense_shares(
                total_amount=Decimal("200.00"),
                split_type=SplitExpense.SplitType.PERCENTAGE,
                participants=[self.p_alice, self.p_bob],
                decimal_places=2,
                values_by_participant_id={
                    self.p_alice.id: Decimal("25"),
                    self.p_bob.id: Decimal("50"),
                },
            )

    def test_shares_split(self):
        shares = compute_expense_shares(
            total_amount=Decimal("100.00"),
            split_type=SplitExpense.SplitType.SHARES,
            participants=[self.p_alice, self.p_bob, self.p_charlie],
            decimal_places=2,
            values_by_participant_id={
                self.p_alice.id: Decimal("2"),
                self.p_bob.id: Decimal("1"),
                self.p_charlie.id: Decimal("1"),
            },
        )
        self.assertEqual(
            [s.amount for s in shares],
            [Decimal("50.00"), Decimal("25.00"), Decimal("25.00")],
        )


class DebtSimplificationTests(SplitTestBase):
    def test_chain_collapses_roundtrip(self):
        """X pays Y's share, Y pays Z's share -> Z pays X directly (1 transfer, no roundtrip)."""
        # Alice pays $30 for Bob only -> Bob owes Alice $30
        e1 = SplitExpense.objects.create(
            event=self.event, paid_by=self.p_alice, description="Dinner", amount=Decimal("30.00")
        )
        SplitExpenseShare.objects.create(expense=e1, participant=self.p_bob, amount=Decimal("30.00"))

        # Bob pays $30 for Charlie only -> Charlie owes Bob $30
        e2 = SplitExpense.objects.create(
            event=self.event, paid_by=self.p_bob, description="Drinks", amount=Decimal("30.00")
        )
        SplitExpenseShare.objects.create(expense=e2, participant=self.p_charlie, amount=Decimal("30.00"))

        summary = get_event_settlement_summary(self.event)
        transfers = summary["transfers"]
        self.assertEqual(len(transfers), 1)
        self.assertEqual(transfers[0].from_participant, self.p_charlie)
        self.assertEqual(transfers[0].to_participant, self.p_alice)
        self.assertEqual(transfers[0].amount, Decimal("30.00"))

    def test_disjoint_zero_sum_subsets_minimizes_transfers(self):
        p_dave = SplitParticipant.objects.create(
            event=self.event, name="Dave", is_external=True
        )
        p_eve = SplitParticipant.objects.create(
            event=self.event, name="Eve", is_external=True
        )
        # Subset 1: Alice +30, Bob -10, Charlie -20 (2 transfers)
        # Subset 2: Dave +15, Eve -15 (1 transfer)
        # Optimal total: 3 transfers (not 4!)
        zero = Decimal("0.00")
        balances = [
            ParticipantBalance(self.p_alice, zero, zero, zero, zero, Decimal("30.00")),
            ParticipantBalance(self.p_bob, zero, zero, zero, zero, Decimal("-10.00")),
            ParticipantBalance(self.p_charlie, zero, zero, zero, zero, Decimal("-20.00")),
            ParticipantBalance(p_dave, zero, zero, zero, zero, Decimal("15.00")),
            ParticipantBalance(p_eve, zero, zero, zero, zero, Decimal("-15.00")),
        ]
        transfers = simplify_debts(balances, decimal_places=2)
        self.assertEqual(len(transfers), 3)

        # Verify applying transfers settles everyone to exactly 0
        net = {b.participant.id: b.net_balance for b in balances}
        for t in transfers:
            net[t.from_participant.id] += t.amount
            net[t.to_participant.id] -= t.amount
        for bal in net.values():
            self.assertEqual(bal, Decimal("0.00"))


class ExternalParticipantAndPortalTests(SplitTestBase):
    def test_external_claim_login_and_isolation(self):
        auth_url = reverse("split_external_auth", kwargs={"share_token": self.event.share_token})
        detail_url = reverse("split_external_event_detail", kwargs={"share_token": self.event.share_token})

        # Unauthenticated external user redirected to auth
        resp = self.client.get(detail_url)
        self.assertRedirects(resp, auth_url)

        # Auth page loads cleanly without firing login-protected /toasts/ HTMX request
        auth_page = self.client.get(auth_url)
        self.assertEqual(auth_page.status_code, 200)
        self.assertNotContains(auth_page, reverse("toasts"))

        # First-time claim: mismatching password rejected
        resp = self.client.post(
            auth_url,
            {
                "participant": self.p_charlie.id,
                "username": "chaz",
                "password": "secret123",
                "password_confirm": "wrong",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.p_charlie.refresh_from_db()
        self.assertFalse(self.p_charlie.is_claimed)

        # First-time claim: matching password succeeds
        resp = self.client.post(
            auth_url,
            {
                "participant": self.p_charlie.id,
                "username": "chaz",
                "password": "secret123",
                "password_confirm": "secret123",
            },
        )
        self.assertRedirects(resp, detail_url)
        self.p_charlie.refresh_from_db()
        self.assertTrue(self.p_charlie.is_claimed)
        self.assertEqual(self.p_charlie.external_username, "chaz")

        # External user is NOT a WYGIWYH user and cannot access WYGIWYH routes
        wygiwyh_resp = self.client.get(reverse("split_event_index"))
        self.assertEqual(wygiwyh_resp.status_code, 302)
        self.assertIn("/login/", wygiwyh_resp["Location"])

        # External user can render the event content fragment
        ext_content_resp = self.client.get(
            reverse(
                "split_external_event_content",
                kwargs={"share_token": self.event.share_token},
            ),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(ext_content_resp.status_code, 200)
        self.assertContains(ext_content_resp, "Beach Trip")

        # External user can add an expense with notes & attachment
        tmp_dir = tempfile.mkdtemp()
        storage = SplitAttachment._meta.get_field("file").storage
        orig_location = storage._location
        storage._location = tmp_dir
        storage.__dict__.pop("location", None)
        try:
            add_url = reverse(
                "split_external_expense_add",
                kwargs={"share_token": self.event.share_token},
            )
            receipt = SimpleUploadedFile("receipt.txt", b"grocery receipt", content_type="text/plain")
            resp = self.client.post(
                add_url,
                {
                    "description": "Groceries",
                    "amount": "90.00",
                    "date": str(timezone.localdate()),
                    "paid_by": self.p_charlie.id,
                    "split_type": SplitExpense.SplitType.EQUAL,
                    "share_participants": [self.p_alice.id, self.p_bob.id, self.p_charlie.id],
                    "notes": "Bought snacks and drinks",
                    "attachments": receipt,
                },
                HTTP_HX_REQUEST="true",
            )
            self.assertEqual(resp.status_code, 204)
            expense = SplitExpense.objects.get(event=self.event, description="Groceries")
            self.assertEqual(expense.notes, "Bought snacks and drinks")
            self.assertEqual(expense.shares.count(), 3)
            self.assertEqual(expense.attachments.count(), 1)

            # External user can download the attachment
            att = expense.attachments.first()
            dl_url = reverse(
                "split_external_attachment_download",
                kwargs={"share_token": self.event.share_token, "attachment_id": att.id},
            )
            dl_resp = self.client.get(dl_url)
            self.assertEqual(dl_resp.status_code, 200)
            self.assertEqual(b"".join(dl_resp.streaming_content), b"grocery receipt")
        finally:
            storage._location = orig_location
            storage.__dict__.pop("location", None)

        # Deactivating Charlie preserves contributions but immediately revokes portal access
        self.p_charlie.is_active = False
        self.p_charlie.save()
        self.assertFalse(self.p_charlie.can_be_deleted())
        resp = self.client.get(detail_url)
        self.assertRedirects(resp, auth_url)

        # Balances still include Charlie's $90 contribution
        balances = {b.participant.id: b for b in calculate_event_balances(self.event)}
        self.assertEqual(balances[self.p_charlie.id].net_balance, Decimal("60.00"))


class WygiwyhSyncTests(SplitTestBase):
    def test_settlement_sync_and_auto_paid_on_payment(self):
        self.client.force_login(self.creator)

        # Bob pays $100 split equally between Alice and Bob -> Alice owes Bob $50
        exp = SplitExpense.objects.create(
            event=self.event,
            paid_by=self.p_bob,
            description="Hotel",
            amount=Decimal("100.00"),
        )
        SplitExpenseShare.objects.create(expense=exp, participant=self.p_alice, amount=Decimal("50.00"))
        SplitExpenseShare.objects.create(expense=exp, participant=self.p_bob, amount=Decimal("50.00"))

        # Alice creates a planned unpaid WYGIWYH transaction to pay Bob $50
        sync_url = (
            reverse("split_sync_settlement", kwargs={"event_id": self.event.id})
            + f"?direction=out&counterparty={self.p_bob.id}&amount=50.00"
        )
        resp = self.client.post(
            sync_url,
            {
                "mode": "create",
                "account": self.account.id,
                "amount": "50.00",
                "date": str(timezone.localdate()),
                "description": "Pay Bob for Beach Trip",
                # is_paid omitted -> False (unpaid)
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 204)

        link = SplitTransactionLink.objects.get(event=self.event, user=self.creator)
        self.assertEqual(link.kind, SplitTransactionLink.Kind.SETTLEMENT_OUT)
        self.assertFalse(link.transaction.is_paid)
        self.assertEqual(link.transaction.type, Transaction.Type.EXPENSE)
        self.assertEqual(link.transaction.amount, Decimal("50.00"))

        # Now Alice records the payment to Bob -> linked WYGIWYH transaction auto-marks as paid!
        pay_url = reverse("split_payment_add", kwargs={"event_id": self.event.id})
        resp = self.client.post(
            pay_url,
            {
                "from_participant": self.p_alice.id,
                "to_participant": self.p_bob.id,
                "amount": "50.00",
                "date": str(timezone.localdate()),
                "notes": "Settled!",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 204)

        link.refresh_from_db()
        link.transaction.refresh_from_db()
        self.assertTrue(link.transaction.is_paid)
        self.assertEqual(link.kind, SplitTransactionLink.Kind.PAYMENT_OUT)
        self.assertIsNotNone(link.payment_id)

        # Event is now completely settled
        summary = get_event_settlement_summary(self.event)
        self.assertEqual(summary["transfers"], [])

    def test_link_existing_transaction_and_unlink(self):
        self.client.force_login(self.creator)
        exp = SplitExpense.objects.create(
            event=self.event,
            paid_by=self.p_alice,
            description="Fuel",
            amount=Decimal("40.00"),
        )
        SplitExpenseShare.objects.create(expense=exp, participant=self.p_alice, amount=Decimal("20.00"))
        SplitExpenseShare.objects.create(expense=exp, participant=self.p_bob, amount=Decimal("20.00"))

        existing_tx = Transaction.objects.create(
            owner=self.creator,
            account=self.account,
            type=Transaction.Type.EXPENSE,
            amount=Decimal("40.00"),
            date=timezone.localdate(),
            description="Gas station",
        )

        sync_url = reverse(
            "split_sync_expense",
            kwargs={"event_id": self.event.id, "expense_id": exp.id},
        )
        resp = self.client.post(
            sync_url,
            {
                "mode": "link",
                "existing_transaction": existing_tx.id,
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 204)
        link = SplitTransactionLink.objects.get(event=self.event, expense=exp)
        self.assertEqual(link.transaction_id, existing_tx.id)

        # Unlinking removes the link but keeps the WYGIWYH transaction intact
        unlink_url = reverse(
            "split_sync_unlink",
            kwargs={"event_id": self.event.id, "link_id": link.id},
        )
        resp = self.client.delete(unlink_url, HTTP_HX_REQUEST="true")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(SplitTransactionLink.objects.filter(id=link.id).exists())
        self.assertTrue(Transaction.objects.filter(id=existing_tx.id).exists())

    def test_creator_can_remove_unused_or_deactivate_used_participant(self):
        self.client.force_login(self.creator)
        unused = SplitParticipant.objects.create(
            event=self.event, name="Unused Guest", is_external=True
        )
        del_url = reverse(
            "split_participant_delete",
            kwargs={"event_id": self.event.id, "participant_id": unused.id},
        )
        resp = self.client.delete(del_url, HTTP_HX_REQUEST="true")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(SplitParticipant.objects.filter(id=unused.id).exists())

        # Regenerating share link updates UUID
        old_token = self.event.share_token
        regen_url = reverse("split_event_regenerate_link", kwargs={"event_id": self.event.id})
        resp = self.client.post(regen_url, HTTP_HX_REQUEST="true")
        self.assertEqual(resp.status_code, 200)
        self.event.refresh_from_db()
        self.assertNotEqual(self.event.share_token, old_token)

        # WYGIWYH user can render event list and event content fragments
        list_resp = self.client.get(reverse("split_event_list"), HTTP_HX_REQUEST="true")
        self.assertEqual(list_resp.status_code, 200)
        self.assertContains(list_resp, "Beach Trip")

        content_resp = self.client.get(
            reverse("split_event_content", kwargs={"event_id": self.event.id}),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(content_resp.status_code, 200)
        self.assertContains(content_resp, "Beach Trip")
        self.assertNotContains(content_resp, 'data-original-amount="ERR"')

        # Expense form uses Alpine x-mask on amount input
        exp_form_resp = self.client.get(
            reverse("split_expense_add", kwargs={"event_id": self.event.id}),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(exp_form_resp.status_code, 200)
        self.assertContains(exp_form_resp, "x-mask:dynamic")


class RegressionTests(SplitTestBase):
    def test_password_reset_signs_out_existing_external_sessions(self):
        token = self.event.share_token
        self.p_charlie.set_external_password("secret123")
        self.client.post(
            reverse("split_external_auth", kwargs={"share_token": token}),
            {"participant": self.p_charlie.id, "password": "secret123"},
        )
        detail_url = reverse("split_external_event_detail", kwargs={"share_token": token})
        self.assertEqual(self.client.get(detail_url).status_code, 200)

        # Organizer resets, the real Charlie claims again: the old session must stay dead
        self.p_charlie.reset_external_password()
        self.p_charlie.set_external_password("newpass99")
        self.assertEqual(self.client.get(detail_url).status_code, 302)

    def test_untrusted_attachment_types_are_downloaded_not_rendered(self):
        self.client.force_login(self.creator)
        expense = SplitExpense.objects.create(
            event=self.event, paid_by=self.p_charlie, description="x", amount=Decimal("1")
        )
        storage = SplitAttachment._meta.get_field("file").storage
        orig_location = storage._location
        storage._location = tempfile.mkdtemp()
        storage.__dict__.pop("location", None)
        try:
            for content_type, inline in (
                ("text/html", False),
                ("image/svg+xml", False),
                ("image/png", True),
            ):
                att = SplitAttachment.objects.create(
                    event=self.event,
                    expense=expense,
                    file=SimpleUploadedFile("f", b"x", content_type=content_type),
                    original_name="f",
                    content_type=content_type,
                )
                resp = self.client.get(
                    reverse(
                        "split_attachment_download",
                        kwargs={"event_id": self.event.id, "attachment_id": att.id},
                    )
                )
                self.assertEqual(
                    resp["Content-Disposition"].startswith("inline"), inline, content_type
                )
        finally:
            storage._location = orig_location
            storage.__dict__.pop("location", None)

    def test_split_values_ignore_locale_thousand_separator(self):
        self.client.force_login(self.creator)
        pt_br = {"THOUSAND_SEPARATOR": ".", "DECIMAL_SEPARATOR": ","}
        with patch("apps.common.widgets.decimal.get_format", side_effect=pt_br.get):
            resp = self.client.post(
                reverse("split_expense_add", kwargs={"event_id": self.event.id}),
                {
                    "description": "Dinner",
                    "amount": "20",
                    "date": str(timezone.localdate()),
                    "paid_by": self.p_alice.id,
                    "split_type": SplitExpense.SplitType.EXACT,
                    "share_participants": [self.p_alice.id, self.p_bob.id],
                    f"share_value_{self.p_alice.id}": "12.5",
                    f"share_value_{self.p_bob.id}": "7.5",
                },
                HTTP_HX_REQUEST="true",
            )
        self.assertEqual(resp.status_code, 204)
        shares = SplitExpenseShare.objects.filter(expense__description="Dinner")
        self.assertEqual(
            {s.participant_id: s.amount for s in shares},
            {self.p_alice.id: Decimal("12.5"), self.p_bob.id: Decimal("7.5")},
        )

    def test_cannot_sync_money_that_did_not_move_through_your_accounts(self):
        self.client.force_login(self.creator)
        payment = SplitPayment.objects.create(
            event=self.event,
            from_participant=self.p_bob,
            to_participant=self.p_charlie,
            amount=Decimal("5"),
        )
        expense = SplitExpense.objects.create(
            event=self.event, paid_by=self.p_bob, description="x", amount=Decimal("5")
        )
        for url in (
            reverse("split_sync_payment", kwargs={"event_id": self.event.id, "payment_id": payment.id}),
            reverse("split_sync_expense", kwargs={"event_id": self.event.id, "expense_id": expense.id}),
        ):
            self.assertEqual(self.client.get(url, HTTP_HX_REQUEST="true").status_code, 404)

    def test_currency_locked_once_event_has_expenses(self):
        from apps.splits.forms import SplitEventForm

        self.assertFalse(SplitEventForm(instance=self.event).fields["currency"].disabled)
        SplitExpense.objects.create(
            event=self.event, paid_by=self.p_alice, description="x", amount=Decimal("5")
        )
        self.assertTrue(SplitEventForm(instance=self.event).fields["currency"].disabled)


class LeaveEventTests(SplitTestBase):
    def _leave(self, user):
        self.client.force_login(user)
        return self.client.post(
            reverse("split_event_leave", kwargs={"event_id": self.event.id}),
            HTTP_HX_REQUEST="true",
        )

    def test_member_without_contributions_is_removed(self):
        resp = self._leave(self.other_user)
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(SplitParticipant.objects.filter(id=self.p_bob.id).exists())
        self.assertFalse(self.event.is_accessible_by_user(self.other_user))

    def test_member_with_contributions_is_deactivated_and_balances_kept(self):
        exp = SplitExpense.objects.create(
            event=self.event, paid_by=self.p_bob, description="x", amount=Decimal("10")
        )
        SplitExpenseShare.objects.create(expense=exp, participant=self.p_alice, amount=Decimal("10"))
        self._leave(self.other_user)
        self.p_bob.refresh_from_db()
        self.assertFalse(self.p_bob.is_active)
        self.assertFalse(self.event.is_accessible_by_user(self.other_user))
        balances = {b.participant.id: b for b in calculate_event_balances(self.event)}
        self.assertEqual(balances[self.p_bob.id].net_balance, Decimal("10.00"))

    def test_organizer_cannot_leave(self):
        self.assertEqual(self._leave(self.creator).status_code, 403)


class SyncLinkPickerTests(SplitTestBase):
    def test_link_rejects_wrong_type_or_currency(self):
        self.client.force_login(self.creator)
        exp = SplitExpense.objects.create(
            event=self.event, paid_by=self.p_alice, description="x", amount=Decimal("5")
        )
        income = Transaction.objects.create(
            owner=self.creator, account=self.account, type=Transaction.Type.INCOME,
            amount=Decimal("5"), date=timezone.localdate(),
        )
        resp = self.client.post(
            reverse("split_sync_expense", kwargs={"event_id": self.event.id, "expense_id": exp.id}),
            {"mode": "link", "existing_transaction": income.id},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(SplitTransactionLink.objects.exists())


class PaymentPermissionAndReportTests(SplitTestBase):
    def _record(self, user, from_p, to_p):
        self.client.force_login(user)
        return self.client.post(
            reverse("split_payment_add", kwargs={"event_id": self.event.id}),
            {
                "from_participant": from_p.id,
                "to_participant": to_p.id,
                "amount": "5",
                "date": str(timezone.localdate()),
            },
            HTTP_HX_REQUEST="true",
        )

    def test_only_involved_people_or_organizer_can_record_payment(self):
        # Bob is neither sender nor recipient, nor the organizer
        self.assertEqual(self._record(self.other_user, self.p_charlie, self.p_alice).status_code, 200)
        self.assertFalse(SplitPayment.objects.exists())
        # Bob paying someone is fine
        self.assertEqual(self._record(self.other_user, self.p_bob, self.p_charlie).status_code, 204)
        # The organizer can record a payment between two others
        self.assertEqual(self._record(self.creator, self.p_charlie, self.p_bob).status_code, 204)

    def test_report_renders_for_members_and_external_participants(self):
        self.client.force_login(self.creator)
        resp = self.client.get(reverse("split_event_report", kwargs={"event_id": self.event.id}))
        self.assertContains(resp, "Beach Trip")

        self.client.logout()
        token = self.event.share_token
        self.p_charlie.set_external_password("secret123")
        self.client.post(
            reverse("split_external_auth", kwargs={"share_token": token}),
            {"participant": self.p_charlie.id, "password": "secret123"},
        )
        resp = self.client.get(reverse("split_external_event_report", kwargs={"share_token": token}))
        self.assertContains(resp, "Beach Trip")
