"""Object-level authorization tests for the transaction-rule endpoints.

Regression coverage for GHSA-83g9-vjqf-2j5q: SharedObjectManager scopes rules to
what a user may *see*, which included other people's public and shared-with-them
rules. Several mutating endpoints treated that visibility as permission to write.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.rules.models import (
    TransactionRule,
    TransactionRuleAction,
    UpdateOrCreateTransactionRuleAction,
)

HTMX = {"HTTP_HX_REQUEST": "true"}


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
class TransactionRuleObjectPermissionTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="owner@test.com", password="testpass123"
        )
        self.shared_user = User.objects.create_user(
            email="shared@test.com", password="testpass123"
        )
        self.stranger = User.objects.create_user(
            email="stranger@test.com", password="testpass123"
        )

        # Public: visible to everyone through SharedObjectManager.
        self.public_rule = TransactionRule.all_objects.create(
            name="Public rule",
            trigger="True",
            owner=self.owner,
            visibility="public",
            active=True,
        )
        # Private but shared with shared_user: visible to them, not to stranger.
        self.shared_rule = TransactionRule.all_objects.create(
            name="Shared rule",
            trigger="True",
            owner=self.owner,
            visibility="private",
            active=True,
        )
        self.shared_rule.shared_with.add(self.shared_user)
        # Private and unshared: invisible to everyone but the owner.
        self.private_rule = TransactionRule.all_objects.create(
            name="Private rule",
            trigger="True",
            owner=self.owner,
            visibility="private",
            active=True,
        )

        self.public_action = TransactionRuleAction.objects.create(
            rule=self.public_rule, field="notes", value="owned by owner"
        )
        self.private_action = TransactionRuleAction.objects.create(
            rule=self.private_rule, field="notes", value="owned by owner"
        )
        self.public_linked_action = UpdateOrCreateTransactionRuleAction.objects.create(
            rule=self.public_rule
        )
        self.private_linked_action = UpdateOrCreateTransactionRuleAction.objects.create(
            rule=self.private_rule
        )

    def login(self, user):
        self.client.force_login(user)

    # ------------------------------------------------------------------
    # toggle-active
    # ------------------------------------------------------------------
    def test_stranger_cannot_toggle_public_rule(self):
        self.login(self.stranger)

        response = self.client.get(
            reverse(
                "transaction_rule_toggle_activity",
                kwargs={"transaction_rule_id": self.public_rule.id},
            ),
            **HTMX,
        )

        self.assertEqual(response.status_code, 403)
        self.public_rule.refresh_from_db()
        self.assertTrue(self.public_rule.active)

    def test_shared_user_cannot_toggle_shared_rule(self):
        self.login(self.shared_user)

        response = self.client.get(
            reverse(
                "transaction_rule_toggle_activity",
                kwargs={"transaction_rule_id": self.shared_rule.id},
            ),
            **HTMX,
        )

        self.assertEqual(response.status_code, 403)
        self.shared_rule.refresh_from_db()
        self.assertTrue(self.shared_rule.active)

    def test_owner_can_toggle_own_rule(self):
        self.login(self.owner)

        response = self.client.get(
            reverse(
                "transaction_rule_toggle_activity",
                kwargs={"transaction_rule_id": self.public_rule.id},
            ),
            **HTMX,
        )

        self.assertEqual(response.status_code, 204)
        self.public_rule.refresh_from_db()
        self.assertFalse(self.public_rule.active)

    # ------------------------------------------------------------------
    # rule actions
    # ------------------------------------------------------------------
    def test_stranger_cannot_add_action_to_public_rule(self):
        self.login(self.stranger)

        response = self.client.post(
            reverse(
                "transaction_rule_action_add",
                kwargs={"transaction_rule_id": self.public_rule.id},
            ),
            data={"field": "notes", "value": "injected", "order": 0},
            **HTMX,
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            TransactionRuleAction.objects.filter(value="injected").exists()
        )

    def test_stranger_cannot_edit_action_on_public_rule(self):
        self.login(self.stranger)

        response = self.client.post(
            reverse(
                "transaction_rule_action_edit",
                kwargs={"transaction_rule_action_id": self.public_action.id},
            ),
            data={"field": "notes", "value": "rewritten", "order": 0},
            **HTMX,
        )

        self.assertEqual(response.status_code, 403)
        self.public_action.refresh_from_db()
        self.assertEqual(self.public_action.value, "owned by owner")

    def test_stranger_cannot_delete_action_on_public_rule(self):
        self.login(self.stranger)

        response = self.client.delete(
            reverse(
                "transaction_rule_action_delete",
                kwargs={"transaction_rule_action_id": self.public_action.id},
            ),
            **HTMX,
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(
            TransactionRuleAction.objects.filter(pk=self.public_action.pk).exists()
        )

    def test_stranger_cannot_delete_action_on_invisible_rule(self):
        """The child manager is unscoped, so the id is reachable by guessing.

        The parent rule is invisible to the stranger, so the response must be a
        404 rather than a 403 that confirms the action exists.
        """
        self.login(self.stranger)

        response = self.client.delete(
            reverse(
                "transaction_rule_action_delete",
                kwargs={"transaction_rule_action_id": self.private_action.id},
            ),
            **HTMX,
        )

        self.assertEqual(response.status_code, 404)
        self.assertTrue(
            TransactionRuleAction.objects.filter(pk=self.private_action.pk).exists()
        )

    def test_owner_can_delete_own_action(self):
        self.login(self.owner)

        response = self.client.delete(
            reverse(
                "transaction_rule_action_delete",
                kwargs={"transaction_rule_action_id": self.public_action.id},
            ),
            **HTMX,
        )

        self.assertEqual(response.status_code, 204)
        self.assertFalse(
            TransactionRuleAction.objects.filter(pk=self.public_action.pk).exists()
        )

    # ------------------------------------------------------------------
    # update-or-create rule actions
    # ------------------------------------------------------------------
    def test_stranger_cannot_add_linked_action_to_public_rule(self):
        self.login(self.stranger)

        response = self.client.post(
            reverse(
                "update_or_create_transaction_rule_action_add",
                kwargs={"transaction_rule_id": self.public_rule.id},
            ),
            data={},
            **HTMX,
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            UpdateOrCreateTransactionRuleAction.objects.filter(
                rule=self.public_rule
            ).count(),
            1,
        )

    def test_stranger_cannot_edit_linked_action_on_public_rule(self):
        self.login(self.stranger)

        response = self.client.post(
            reverse(
                "update_or_create_transaction_rule_action_edit",
                kwargs={"pk": self.public_linked_action.id},
            ),
            data={"filter": "injected"},
            **HTMX,
        )

        self.assertEqual(response.status_code, 403)
        self.public_linked_action.refresh_from_db()
        self.assertEqual(self.public_linked_action.filter, "")

    def test_stranger_cannot_delete_linked_action_on_public_rule(self):
        self.login(self.stranger)

        response = self.client.delete(
            reverse(
                "update_or_create_transaction_rule_action_delete",
                kwargs={"pk": self.public_linked_action.id},
            ),
            **HTMX,
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(
            UpdateOrCreateTransactionRuleAction.objects.filter(
                pk=self.public_linked_action.pk
            ).exists()
        )

    def test_stranger_cannot_delete_linked_action_on_invisible_rule(self):
        self.login(self.stranger)

        response = self.client.delete(
            reverse(
                "update_or_create_transaction_rule_action_delete",
                kwargs={"pk": self.private_linked_action.id},
            ),
            **HTMX,
        )

        self.assertEqual(response.status_code, 404)
        self.assertTrue(
            UpdateOrCreateTransactionRuleAction.objects.filter(
                pk=self.private_linked_action.pk
            ).exists()
        )

    # ------------------------------------------------------------------
    # edit / share / dry-run
    # ------------------------------------------------------------------
    def test_stranger_cannot_edit_public_rule(self):
        self.login(self.stranger)

        response = self.client.post(
            reverse(
                "transaction_rule_edit",
                kwargs={"transaction_rule_id": self.public_rule.id},
            ),
            data={"name": "hijacked", "trigger": "True", "order": 0},
            **HTMX,
        )

        self.assertEqual(response.status_code, 403)
        self.public_rule.refresh_from_db()
        self.assertEqual(self.public_rule.name, "Public rule")

    def test_stranger_cannot_change_sharing_of_public_rule(self):
        self.login(self.stranger)

        response = self.client.post(
            reverse(
                "transaction_rule_share_settings", kwargs={"pk": self.public_rule.id}
            ),
            data={"visibility": "private"},
            **HTMX,
        )

        self.assertEqual(response.status_code, 403)
        self.public_rule.refresh_from_db()
        self.assertEqual(self.public_rule.visibility, "public")

    def test_stranger_cannot_dry_run_public_rule(self):
        self.login(self.stranger)

        response = self.client.get(
            reverse(
                "transaction_rule_dry_run_created", kwargs={"pk": self.public_rule.id}
            ),
            **HTMX,
        )

        self.assertEqual(response.status_code, 403)

    # ------------------------------------------------------------------
    # delete: sharing may be revoked, ownership may not be overridden
    # ------------------------------------------------------------------
    def test_stranger_cannot_delete_public_rule(self):
        """The original condition fell through to delete() for public rules."""
        self.login(self.stranger)

        response = self.client.delete(
            reverse(
                "transaction_rule_delete",
                kwargs={"transaction_rule_id": self.public_rule.id},
            ),
            **HTMX,
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(
            TransactionRule.all_objects.filter(pk=self.public_rule.pk).exists()
        )

    def test_shared_user_deleting_only_revokes_their_own_access(self):
        self.login(self.shared_user)

        response = self.client.delete(
            reverse(
                "transaction_rule_delete",
                kwargs={"transaction_rule_id": self.shared_rule.id},
            ),
            **HTMX,
        )

        self.assertEqual(response.status_code, 204)
        self.assertTrue(
            TransactionRule.all_objects.filter(pk=self.shared_rule.pk).exists()
        )
        self.assertNotIn(self.shared_user, self.shared_rule.shared_with.all())

    def test_owner_can_delete_own_rule(self):
        self.login(self.owner)

        response = self.client.delete(
            reverse(
                "transaction_rule_delete",
                kwargs={"transaction_rule_id": self.public_rule.id},
            ),
            **HTMX,
        )

        self.assertEqual(response.status_code, 204)
        self.assertFalse(
            TransactionRule.all_objects.filter(pk=self.public_rule.pk).exists()
        )

    # ------------------------------------------------------------------
    # reads must keep working for shared users
    # ------------------------------------------------------------------
    def test_shared_user_can_still_view_shared_rule(self):
        self.login(self.shared_user)

        response = self.client.get(
            reverse(
                "transaction_rule_view",
                kwargs={"transaction_rule_id": self.shared_rule.id},
            ),
            **HTMX,
        )

        self.assertEqual(response.status_code, 200)

    def test_stranger_can_view_public_rule(self):
        self.login(self.stranger)

        response = self.client.get(
            reverse(
                "transaction_rule_view",
                kwargs={"transaction_rule_id": self.public_rule.id},
            ),
            **HTMX,
        )

        self.assertEqual(response.status_code, 200)

    def test_stranger_cannot_view_private_rule(self):
        self.login(self.stranger)

        response = self.client.get(
            reverse(
                "transaction_rule_view",
                kwargs={"transaction_rule_id": self.private_rule.id},
            ),
            **HTMX,
        )

        self.assertEqual(response.status_code, 404)

    # ------------------------------------------------------------------
    # take ownership stays available for unowned rules only
    # ------------------------------------------------------------------
    def test_take_ownership_of_unowned_rule_still_works(self):
        unowned = TransactionRule.all_objects.create(
            name="Legacy rule", trigger="True", owner=None, visibility="private"
        )
        self.login(self.stranger)

        response = self.client.get(
            reverse(
                "transaction_rule_take_ownership",
                kwargs={"transaction_rule_id": unowned.id},
            ),
            **HTMX,
        )

        self.assertEqual(response.status_code, 204)
        unowned.refresh_from_db()
        self.assertEqual(unowned.owner, self.stranger)

    def test_cannot_take_ownership_of_someone_elses_public_rule(self):
        self.login(self.stranger)

        response = self.client.get(
            reverse(
                "transaction_rule_take_ownership",
                kwargs={"transaction_rule_id": self.public_rule.id},
            ),
            **HTMX,
        )

        self.assertEqual(response.status_code, 403)
        self.public_rule.refresh_from_db()
        self.assertEqual(self.public_rule.owner, self.owner)
