"""Delete semantics for every SharedObject-backed model.

Each of these views carried the same inverted condition::

    if obj.owner != request.user and request.user in obj.shared_with.all():
        obj.shared_with.remove(request.user)   # unshare
    else:
        obj.delete()                           # <- public objects landed here

so an object its owner had made public could be destroyed by any authenticated
user. The rule is: the owner deletes, a shared user revokes only their own
access, and nobody else may do either.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Account, AccountGroup
from apps.currencies.models import Currency
from apps.dca.models import DCAStrategy
from apps.rules.models import TransactionRule
from apps.transactions.models import (
    TransactionCategory,
    TransactionEntity,
    TransactionTag,
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
class SharedObjectDeletionTests(TestCase):
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
        self.currency = Currency.objects.create(
            code="USD", name="US Dollar", decimal_places=2
        )

    def cases(self):
        """(label, model, delete url name, url kwarg, extra create kwargs)."""
        return [
            (
                "account",
                Account,
                "account_delete",
                "pk",
                {"currency": self.currency},
            ),
            ("account group", AccountGroup, "account_group_delete", "pk", {}),
            (
                "category",
                TransactionCategory,
                "category_delete",
                "category_id",
                {},
            ),
            ("tag", TransactionTag, "tag_delete", "tag_id", {}),
            ("entity", TransactionEntity, "entity_delete", "entity_id", {}),
            (
                "rule",
                TransactionRule,
                "transaction_rule_delete",
                "transaction_rule_id",
                {"trigger": "True"},
            ),
            (
                "dca strategy",
                DCAStrategy,
                "dca_strategy_delete",
                "strategy_id",
                {
                    "target_currency": self.currency,
                    "payment_currency": self.currency,
                },
            ),
        ]

    def make(self, model, visibility, extra):
        return model.all_objects.create(
            name="Target", owner=self.owner, visibility=visibility, **extra
        )

    def delete(self, url_name, kwarg, obj):
        return self.client.delete(reverse(url_name, kwargs={kwarg: obj.id}), **HTMX)

    def test_stranger_cannot_delete_a_public_object(self):
        for label, model, url_name, kwarg, extra in self.cases():
            with self.subTest(model=label):
                obj = self.make(model, "public", extra)
                self.client.force_login(self.stranger)

                response = self.delete(url_name, kwarg, obj)

                self.assertEqual(response.status_code, 403, label)
                self.assertTrue(
                    model.all_objects.filter(pk=obj.pk).exists(),
                    f"{label} was deleted by a non-owner",
                )

    def test_shared_user_deleting_only_revokes_their_own_access(self):
        for label, model, url_name, kwarg, extra in self.cases():
            with self.subTest(model=label):
                obj = self.make(model, "private", extra)
                obj.shared_with.add(self.shared_user)
                self.client.force_login(self.shared_user)

                response = self.delete(url_name, kwarg, obj)

                self.assertEqual(response.status_code, 204, label)
                self.assertTrue(
                    model.all_objects.filter(pk=obj.pk).exists(),
                    f"{label} was deleted by a shared user",
                )
                self.assertNotIn(self.shared_user, obj.shared_with.all())

    def test_owner_can_delete(self):
        for label, model, url_name, kwarg, extra in self.cases():
            with self.subTest(model=label):
                obj = self.make(model, "private", extra)
                self.client.force_login(self.owner)

                response = self.delete(url_name, kwarg, obj)

                self.assertEqual(response.status_code, 204, label)
                self.assertFalse(
                    model.all_objects.filter(pk=obj.pk).exists(),
                    f"{label} was not deleted by its owner",
                )

    def test_unowned_objects_stay_deletable(self):
        """Legacy objects with no owner are editable by everyone by design."""
        for label, model, url_name, kwarg, extra in self.cases():
            with self.subTest(model=label):
                obj = model.all_objects.create(
                    name="Legacy", owner=None, visibility="private", **extra
                )
                self.client.force_login(self.stranger)

                response = self.delete(url_name, kwarg, obj)

                self.assertEqual(response.status_code, 204, label)
                self.assertFalse(model.all_objects.filter(pk=obj.pk).exists(), label)
