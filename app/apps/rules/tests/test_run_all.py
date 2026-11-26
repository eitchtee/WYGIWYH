"""Running rules by hand against all existing transactions."""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase, override_settings
from django.urls import reverse
from procrastinate.exceptions import AlreadyEnqueued

from apps.accounts.models import Account
from apps.currencies.models import Currency
from apps.rules.models import (
    RuleRun,
    TransactionRule,
    TransactionRuleAction,
    UpdateOrCreateTransactionRuleAction,
)
from apps.rules.tasks import run_rules_on_all_transactions
from apps.transactions.models import Transaction, TransactionTag

HTMX = {"HTTP_HX_REQUEST": "true"}


class RunRulesTestMixin:
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            email="run@example.com", password="testpass123"
        )
        self.other_user = User.objects.create_user(
            email="other@example.com", password="testpass123"
        )
        self.currency = Currency.objects.create(
            code="USD", name="US Dollar", decimal_places=2
        )
        self.account = Account.objects.create(
            name="Main", currency=self.currency, owner=self.user
        )
        self.other_account = Account.objects.create(
            name="Other", currency=self.currency, owner=self.other_user
        )

    def make_transaction(self, description, day=date(2026, 1, 15), **kwargs):
        kwargs.setdefault("account", self.account)
        return Transaction.userless_all_objects.create(
            type=Transaction.Type.EXPENSE,
            amount=Decimal("10.00"),
            date=day,
            description=description,
            **kwargs,
        )

    def make_rule(self, trigger="True", actions=(), **kwargs):
        kwargs.setdefault("owner", self.user)
        rule = TransactionRule.all_objects.create(
            name="Rule", trigger=trigger, **kwargs
        )
        for field, value in actions:
            TransactionRuleAction.objects.create(rule=rule, field=field, value=value)
        return rule

    def make_run(self, *rules, **kwargs):
        kwargs.setdefault("owner", self.user)
        return RuleRun.objects.create(
            rules=[
                {"id": rule.id, "name": rule.name, "applied": 0, "failed": 0}
                for rule in rules
            ],
            **kwargs,
        )

    def run_rules(self, *rules):
        run = self.make_run(*rules)
        run_rules_on_all_transactions(run_id=run.id)
        run.refresh_from_db()
        return run


@patch("apps.rules.signals.check_for_transaction_rules.defer")
class RunRulesOnAllTransactionsTests(RunRulesTestMixin, TransactionTestCase):
    def test_applies_to_old_and_future_transactions_that_match(self, _defer):
        old = self.make_transaction("match", day=date(2001, 1, 1))
        future = self.make_transaction("match", day=date(2040, 1, 1))
        unmatched = self.make_transaction("nope")
        rule = self.make_rule("description == 'match'", actions=[("notes", "'done'")])

        run = self.run_rules(rule)

        for transaction in (old, future, unmatched):
            transaction.refresh_from_db()
        self.assertEqual(
            (old.notes, future.notes, unmatched.notes), ("done", "done", "")
        )
        self.assertEqual(run.status, RuleRun.Status.FINISHED)
        self.assertIsNotNone(run.finished_at)
        self.assertEqual(
            (run.total, run.processed, run.applied, run.failed, run.unchanged),
            (3, 3, 2, 0, 1),
        )
        self.assertEqual((run.rules[0]["applied"], run.rules[0]["failed"]), (2, 0))

    def test_runs_inactive_rules_but_only_the_selected_ones(self, _defer):
        transaction = self.make_transaction("a")
        selected = self.make_rule(
            active=False, on_create=False, actions=[("notes", "'selected'")]
        )
        self.make_rule(actions=[("description", "'not selected'")])

        self.run_rules(selected)

        transaction.refresh_from_db()
        self.assertEqual(
            (transaction.notes, transaction.description), ("selected", "a")
        )

    def test_does_not_touch_inaccessible_or_deleted_transactions(self, _defer):
        hidden = self.make_transaction("a", account=self.other_account)
        deleted = self.make_transaction("a", deleted=True)
        rule = self.make_rule(actions=[("notes", "'changed'")])

        run = self.run_rules(rule)

        self.assertEqual(run.total, 0)
        for transaction in (hidden, deleted):
            self.assertEqual(
                Transaction.userless_all_objects.get(pk=transaction.pk).notes, ""
            )

    def test_ignores_rules_the_user_cannot_see(self, _defer):
        transaction = self.make_transaction("a")
        rule = self.make_rule(owner=self.other_user, actions=[("notes", "'x'")])

        self.run_rules(rule)

        transaction.refresh_from_db()
        self.assertEqual(transaction.notes, "")

    def test_public_rules_of_other_users_do_not_run(self, _defer):
        transaction = self.make_transaction("a")
        public = self.make_rule(
            owner=self.other_user, visibility="public", actions=[("notes", "'x'")]
        )
        shared = self.make_rule(
            owner=self.other_user, actions=[("description", "'shared'")]
        )
        shared.shared_with.add(self.user)

        self.run_rules(public, shared)

        transaction.refresh_from_db()
        self.assertEqual((transaction.notes, transaction.description), ("", "shared"))

    def test_manual_run_does_not_auto_tag(self, _defer):
        self.make_transaction("a")

        with patch("apps.rules.tasks.apply_auto_tagging") as auto_tagging:
            self.run_rules(self.make_rule())

        auto_tagging.assert_not_called()

    def test_failing_action_leaves_that_rule_unapplied(self, _defer):
        transaction = self.make_transaction("a")
        # Public, so the assertion below can see it outside of a user's context
        tag = TransactionTag.all_objects.create(
            name="keep", owner=self.user, visibility="public"
        )
        transaction.tags.add(tag)
        broken = self.make_rule(
            actions=[("notes", "'partial'"), ("tags", "'does not exist'")]
        )
        working = self.make_rule(order=1, actions=[("description", "'b'")])

        run = self.run_rules(broken, working)

        transaction.refresh_from_db()
        self.assertEqual(list(transaction.tags.all()), [tag])
        self.assertEqual((transaction.notes, transaction.description), ("", "b"))
        self.assertEqual((run.applied, run.failed), (0, 1))
        self.assertEqual(
            [(rule["applied"], rule["failed"]) for rule in run.rules],
            [(0, 1), (1, 0)],
        )
        [failure] = run.failures
        self.assertEqual(failure["transaction_id"], transaction.id)
        self.assertEqual(failure["date"], "2026-01-15")
        self.assertIn("TransactionTag matching query does not exist", failure["error"])

    def test_broken_trigger_does_not_stop_the_run(self, _defer):
        first = self.make_transaction("a")
        second = self.make_transaction("a")
        broken = self.make_rule("old_description == 'a'")
        working = self.make_rule(order=1, actions=[("notes", "'ok'")])

        run = self.run_rules(broken, working)

        for transaction in (first, second):
            transaction.refresh_from_db()
            self.assertEqual(transaction.notes, "ok")
        self.assertEqual(run.failed, 2)
        self.assertIn("old_description", run.failures[0]["error"])

    def test_stored_errors_are_capped(self, _defer):
        for _ in range(3):
            self.make_transaction("a")
        broken = self.make_rule("missing_name")

        with patch.object(RuleRun, "MAX_FAILURES", 2):
            run = self.run_rules(broken)

        self.assertEqual((run.failed, len(run.failures)), (3, 2))

    def test_run_is_marked_failed_if_it_stops(self, _defer):
        run = self.make_run(self.make_rule())

        with patch("apps.rules.tasks._apply_run", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                run_rules_on_all_transactions(run_id=run.id)

        run.refresh_from_db()
        self.assertEqual(run.status, RuleRun.Status.FAILED)
        self.assertIsNotNone(run.finished_at)

    def test_transactions_created_by_the_run_are_not_processed(self, _defer):
        self.make_transaction("a")
        self.make_transaction("a")
        rule = self.make_rule()
        UpdateOrCreateTransactionRuleAction.objects.create(
            rule=rule,
            set_account="account_id",
            set_type="'IN'",
            set_date="date",
            set_amount="amount",
            set_description="'copy'",
        )

        self.run_rules(rule)

        self.assertEqual(
            Transaction.userless_all_objects.filter(description="copy").count(), 2
        )


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
@patch("apps.rules.views.run_rules_on_all_transactions.configure")
class RunRulesViewTests(RunRulesTestMixin, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)
        self.active = self.make_rule()
        self.inactive = self.make_rule(active=False)
        self.delete_only = self.make_rule(on_create=False, on_delete=True)
        self.hidden = self.make_rule(owner=self.other_user)
        # Readable by everyone, but not ours to run
        self.public = self.make_rule(owner=self.other_user, visibility="public")

    def selected(self, url):
        response = self.client.get(url, **HTMX)
        self.assertEqual(response.status_code, 200)
        return [rule.id for rule in response.context["form"]["rules"].initial]

    def test_preselects_active_create_or_update_rules(self, _configure):
        self.assertEqual(self.selected(reverse("rules_run")), [self.active.id])

    def test_preselects_the_requested_rule(self, _configure):
        response = self.client.get(
            reverse("rules_run") + f"?rule={self.inactive.id}", **HTMX
        )

        self.assertEqual(response.context["form"]["rules"].initial, [self.inactive.id])

    def test_post_queues_the_run(self, configure):
        response = self.client.post(
            reverse("rules_run"), {"rules": [self.inactive.id]}, **HTMX
        )

        run = RuleRun.objects.get()
        self.assertEqual(run.owner, self.user)
        self.assertEqual([rule["id"] for rule in run.rules], [self.inactive.id])
        configure.return_value.defer.assert_called_once_with(run_id=run.id)
        self.assertContains(response, reverse("rule_run_progress", args=[run.id]))

    def test_post_rejects_hidden_or_missing_rules(self, configure):
        for data in ({}, {"rules": [self.hidden.id]}, {"rules": [self.public.id]}):
            response = self.client.post(reverse("rules_run"), data, **HTMX)

            self.assertEqual(response.status_code, 200)
        configure.assert_not_called()

    def test_post_reports_an_already_waiting_run(self, configure):
        configure.return_value.defer.side_effect = AlreadyEnqueued

        response = self.client.post(
            reverse("rules_run"), {"rules": [self.active.id]}, **HTMX
        )

        self.assertEqual(response.status_code, 204)
        self.assertFalse(RuleRun.objects.exists())

    def test_progress_is_polled_until_the_run_is_done(self, _configure):
        run = self.make_run(self.active)
        url = reverse("rule_run_progress", args=[run.id])

        self.assertEqual(self.client.get(url, **HTMX).status_code, 200)
        for status in (RuleRun.Status.FINISHED, RuleRun.Status.FAILED):
            RuleRun.objects.filter(id=run.id).update(status=status)

            self.assertEqual(self.client.get(url, **HTMX).status_code, 286)
            detail = self.client.get(reverse("rule_run_detail", args=[run.id]), **HTMX)
            self.assertNotContains(detail, url)

    def test_runs_are_private_to_their_owner(self, _configure):
        run = self.make_run(self.active, owner=self.other_user)

        for name in ("rule_run_detail", "rule_run_progress"):
            response = self.client.get(reverse(name, args=[run.id]), **HTMX)

            self.assertEqual(response.status_code, 404)
        response = self.client.get(reverse("rule_runs_list"), **HTMX)
        self.assertEqual(list(response.context["runs"]), [])

    def test_rules_page_links_to_the_run_form(self, _configure):
        response = self.client.get(reverse("rules_list"), **HTMX)

        self.assertContains(response, f"{reverse('rules_run')}?rule={self.active.id}")
        self.assertNotContains(
            response, f"{reverse('rules_run')}?rule={self.public.id}"
        )
        for rule, assertion in (
            (self.active, self.assertContains),
            (self.public, self.assertNotContains),
        ):
            view = self.client.get(
                reverse("transaction_rule_view", args=[rule.id]), **HTMX
            )
            assertion(view, f"{reverse('rules_run')}?rule={rule.id}")
