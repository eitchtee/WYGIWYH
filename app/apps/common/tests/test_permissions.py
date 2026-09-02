from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import RequestFactory, TestCase, override_settings

from apps.common.functions.permissions import (
    EDIT,
    READ,
    get_shared_object_or_error,
)
from apps.common.middleware.thread_local import delete_current_user, write_current_user
from apps.rules.models import TransactionRule, TransactionRuleAction


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
    WHITENOISE_AUTOREFRESH=True,
)
class SharedObjectPredicateTests(TestCase):
    """Unit tests for is_visible_to / is_editable_by on SharedObject."""

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

    def _rule(self, **kwargs):
        kwargs.setdefault("name", "Rule")
        kwargs.setdefault("trigger", "True")
        return TransactionRule.all_objects.create(**kwargs)

    def test_owner_can_read_and_edit_own_private_rule(self):
        rule = self._rule(owner=self.owner, visibility="private")

        self.assertTrue(rule.is_visible_to(self.owner))
        self.assertTrue(rule.is_editable_by(self.owner))

    def test_private_rule_is_invisible_to_stranger(self):
        rule = self._rule(owner=self.owner, visibility="private")

        self.assertFalse(rule.is_visible_to(self.stranger))
        self.assertFalse(rule.is_editable_by(self.stranger))

    def test_shared_rule_is_readable_but_not_editable(self):
        rule = self._rule(owner=self.owner, visibility="private")
        rule.shared_with.add(self.shared_user)

        self.assertTrue(rule.is_visible_to(self.shared_user))
        self.assertFalse(rule.is_editable_by(self.shared_user))

    def test_public_rule_is_readable_but_not_editable(self):
        rule = self._rule(owner=self.owner, visibility="public")

        self.assertTrue(rule.is_visible_to(self.stranger))
        self.assertFalse(rule.is_editable_by(self.stranger))

    def test_unowned_rule_stays_readable_and_editable_by_everyone(self):
        rule = self._rule(owner=None, visibility="private")

        self.assertTrue(rule.is_visible_to(self.stranger))
        self.assertTrue(rule.is_editable_by(self.stranger))

    def test_anonymous_user_gets_no_access_to_owned_rules(self):
        rule = self._rule(owner=self.owner, visibility="private")

        self.assertFalse(rule.is_visible_to(AnonymousUser()))
        self.assertFalse(rule.is_editable_by(AnonymousUser()))


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
    WHITENOISE_AUTOREFRESH=True,
)
class SharedObjectPredicateParityTests(TestCase):
    """is_visible_to must agree with what SharedObjectManager returns.

    The manager filters at the queryset level and the predicate checks a single
    instance, so the two cannot share an implementation. This asserts they do
    not drift apart.
    """

    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="owner@test.com", password="testpass123"
        )
        self.other = User.objects.create_user(
            email="other@test.com", password="testpass123"
        )
        self.addCleanup(self._clear_current_user)

    def _clear_current_user(self):
        try:
            delete_current_user()
        except AttributeError:
            pass

    def test_manager_and_predicate_agree_over_every_combination(self):
        combinations = []
        for owner in (self.owner, self.other, None):
            for visibility in ("private", "public"):
                for shared in (True, False):
                    rule = TransactionRule.all_objects.create(
                        name=f"{owner}-{visibility}-{shared}",
                        trigger="True",
                        owner=owner,
                        visibility=visibility,
                    )
                    if shared:
                        rule.shared_with.add(self.owner)
                    combinations.append(rule)

        write_current_user(self.owner)
        visible_ids = set(TransactionRule.objects.values_list("id", flat=True))

        for rule in combinations:
            with self.subTest(rule=rule.name):
                self.assertEqual(
                    rule.id in visible_ids,
                    rule.is_visible_to(self.owner),
                    f"manager and is_visible_to disagree for {rule.name}",
                )


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    },
    WHITENOISE_AUTOREFRESH=True,
)
class GetSharedObjectOrErrorTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            email="owner@test.com", password="testpass123"
        )
        self.stranger = User.objects.create_user(
            email="stranger@test.com", password="testpass123"
        )
        self.factory = RequestFactory()

        self.public_rule = TransactionRule.all_objects.create(
            name="Public", trigger="True", owner=self.owner, visibility="public"
        )
        self.private_rule = TransactionRule.all_objects.create(
            name="Private", trigger="True", owner=self.owner, visibility="private"
        )
        self.public_action = TransactionRuleAction.objects.create(
            rule=self.public_rule, field="notes", value="x"
        )
        self.private_action = TransactionRuleAction.objects.create(
            rule=self.private_rule, field="notes", value="x"
        )

        self.addCleanup(self._clear_current_user)

    def _clear_current_user(self):
        try:
            delete_current_user()
        except AttributeError:
            pass

    def _request(self, user):
        request = self.factory.get("/")
        request.user = user
        write_current_user(user)
        return request

    def test_read_allows_visible_object(self):
        request = self._request(self.stranger)

        rule = get_shared_object_or_error(
            TransactionRule, request, id=self.public_rule.id, level=READ
        )

        self.assertEqual(rule, self.public_rule)

    def test_edit_denies_visible_but_unowned_object_with_403(self):
        request = self._request(self.stranger)

        with self.assertRaises(PermissionDenied):
            get_shared_object_or_error(
                TransactionRule, request, id=self.public_rule.id, level=EDIT
            )

    def test_edit_allows_owner(self):
        request = self._request(self.owner)

        rule = get_shared_object_or_error(
            TransactionRule, request, id=self.public_rule.id, level=EDIT
        )

        self.assertEqual(rule, self.public_rule)

    def test_invisible_object_raises_404_not_403(self):
        """403 must not confirm the existence of an object the user cannot see."""
        request = self._request(self.stranger)

        with self.assertRaises(Http404):
            get_shared_object_or_error(
                TransactionRule, request, id=self.private_rule.id, level=EDIT
            )

    def test_via_traverses_to_the_governing_object(self):
        request = self._request(self.stranger)

        with self.assertRaises(PermissionDenied):
            get_shared_object_or_error(
                TransactionRuleAction,
                request,
                id=self.public_action.id,
                level=EDIT,
                via="rule",
            )

    def test_via_hides_children_of_invisible_parents_behind_404(self):
        """TransactionRuleAction has an unscoped manager, so the id is reachable."""
        request = self._request(self.stranger)

        with self.assertRaises(Http404):
            get_shared_object_or_error(
                TransactionRuleAction,
                request,
                id=self.private_action.id,
                level=EDIT,
                via="rule",
            )

    def test_unresolvable_via_path_fails_closed(self):
        """A typo'd path must raise, never silently grant access."""
        request = self._request(self.stranger)

        with self.assertRaises(AttributeError):
            get_shared_object_or_error(
                TransactionRuleAction,
                request,
                id=self.public_action.id,
                level=EDIT,
                via="rulee",
            )

    def test_unknown_level_is_rejected(self):
        request = self._request(self.owner)

        with self.assertRaises(ValueError):
            get_shared_object_or_error(
                TransactionRule, request, id=self.public_rule.id, level="write"
            )
