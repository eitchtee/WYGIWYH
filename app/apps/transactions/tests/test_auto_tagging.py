import datetime
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.models import Account, AccountGroup
from apps.common.middleware.thread_local import (
    delete_current_user,
    get_current_user,
    write_current_user,
)
from apps.currencies.models import Currency
from apps.rules.models import TransactionRule, TransactionRuleAction
from apps.rules.tasks import check_for_transaction_rules
from apps.transactions.auto_tagging.classifier import (
    TrainingRecord,
    TransactionAutoTagger,
)
from apps.transactions.auto_tagging.service import apply_auto_tagging, train_for_user
from apps.transactions.forms import (
    TransactionCategoryForm,
    TransactionEntityForm,
    TransactionTagForm,
)
from apps.transactions.models import (
    AutoTaggerModel,
    Transaction,
    TransactionCategory,
    TransactionEntity,
    TransactionTag,
)
from apps.transactions.tasks import retrain_auto_taggers, train_user_auto_tagger
from apps.users.forms import UserSettingsForm

User = get_user_model()


class TransactionAutoTaggerClassifierTests(TestCase):
    def _sample_records(self) -> list[TrainingRecord]:
        return [
            TrainingRecord(
                description="UBER *TRIP HELP.UBER.COM 12/01",
                notes="",
                account_id=1,
                tx_type="EX",
                amount=Decimal("24.50"),
                category_id=10,
                tag_ids=(100,),
                entity_ids=(200,),
            ),
            TrainingRecord(
                description="UBER *TRIP 15/01/2025",
                notes="",
                account_id=1,
                tx_type="EX",
                amount=Decimal("18.90"),
                category_id=10,
                tag_ids=(100,),
                entity_ids=(200,),
            ),
            TrainingRecord(
                description="UBER *TRIP 2025-01-20",
                notes="",
                account_id=1,
                tx_type="EX",
                amount=Decimal("31.00"),
                category_id=10,
                tag_ids=(100,),
                entity_ids=(200,),
            ),
            TrainingRecord(
                description="PIX PADARIA SÃO JOÃO",
                notes="breakfast",
                account_id=1,
                tx_type="EX",
                amount=Decimal("15.00"),
                category_id=20,
                tag_ids=(101, 102),
                entity_ids=(201,),
            ),
            TrainingRecord(
                description="PIX PADARIA SAO JOAO",
                notes="coffee",
                account_id=1,
                tx_type="EX",
                amount=Decimal("12.00"),
                category_id=20,
                tag_ids=(101, 102),
                entity_ids=(201,),
            ),
        ]

    def test_predicts_category_tags_and_entities_with_noise_and_accents(self):
        tagger = TransactionAutoTagger.fit(self._sample_records())

        uber_pred = tagger.predict(
            description="UBER *TRIP 03/02/2025",
            notes="",
            account_id=1,
            tx_type="EX",
            amount=Decimal("22.00"),
        )
        self.assertEqual(uber_pred.category_id, 10)
        self.assertEqual(uber_pred.tag_ids, (100,))
        self.assertEqual(uber_pred.entity_ids, (200,))

        bakery_pred = tagger.predict(
            description="PIX PADARIA SAO JOAO 04/02",
            notes="",
            account_id=1,
            tx_type="EX",
            amount=Decimal("14.00"),
        )
        self.assertEqual(bakery_pred.category_id, 20)
        self.assertEqual(bakery_pred.tag_ids, (101, 102))
        self.assertEqual(bakery_pred.entity_ids, (201,))

    def test_serialization_roundtrip_and_invalid_blob(self):
        tagger = TransactionAutoTagger.fit(self._sample_records())
        blob = tagger.to_bytes()
        restored = TransactionAutoTagger.from_bytes(blob)

        self.assertIsNotNone(restored)
        self.assertEqual(restored.num_docs, tagger.num_docs)
        pred = restored.predict(
            description="UBER *TRIP",
            notes="",
            account_id=1,
            tx_type="EX",
            amount=Decimal("20.00"),
        )
        self.assertEqual(pred.category_id, 10)

        self.assertIsNone(TransactionAutoTagger.from_bytes(b""))
        self.assertIsNone(TransactionAutoTagger.from_bytes(b"not-valid-zlib"))

    def test_abstains_on_empty_text_or_unrelated_description(self):
        tagger = TransactionAutoTagger.fit(self._sample_records())

        empty_pred = tagger.predict(
            description="",
            notes="",
            account_id=1,
            tx_type="EX",
            amount=Decimal("20.00"),
        )
        self.assertTrue(empty_pred.is_empty)

        unrelated_pred = tagger.predict(
            description="COMPLETELY UNKNOWN MERCHANT XYZ",
            notes="",
            account_id=1,
            tx_type="EX",
            amount=Decimal("20.00"),
        )
        self.assertTrue(unrelated_pred.is_empty)

        # Sharing only 1 weak token among mostly unknown words must still abstain
        weak_overlap_pred = tagger.predict(
            description="COMPLETELY RANDOM TRIP THING",
            notes="",
            account_id=1,
            tx_type="EX",
            amount=Decimal("20.00"),
        )
        self.assertTrue(weak_overlap_pred.is_empty)

    def test_unique_notes_do_not_discard_matching_description(self):
        tagger = TransactionAutoTagger.fit(self._sample_records())

        pred = tagger.predict(
            description="UBER *TRIP 05/02",
            notes="airport pickup for visiting cousins with heavy suitcases",
            account_id=1,
            tx_type="EX",
            amount=Decimal("25.00"),
        )
        self.assertEqual(pred.category_id, 10)
        self.assertEqual(pred.tag_ids, (100,))
        self.assertEqual(pred.entity_ids, (200,))

    def test_respects_allowed_label_sets(self):
        tagger = TransactionAutoTagger.fit(self._sample_records())
        pred = tagger.predict(
            description="UBER *TRIP",
            notes="",
            account_id=1,
            tx_type="EX",
            amount=Decimal("20.00"),
            allowed_category_ids=set(),
            allowed_tag_ids={100},
            allowed_entity_ids=set(),
        )
        self.assertIsNone(pred.category_id)
        self.assertEqual(pred.tag_ids, (100,))
        self.assertEqual(pred.entity_ids, ())


class AutoTaggingServiceAndRulesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="alice@example.com", password="password123"
        )
        self.other_user = User.objects.create_user(
            email="bob@example.com", password="password123"
        )

        self.currency = Currency.objects.create(
            code="USD", name="US Dollar", decimal_places=2, prefix="$ "
        )
        self.group = AccountGroup.objects.create(name="Checking", owner=self.user)
        self.account = Account.objects.create(
            name="Main Card",
            group=self.group,
            currency=self.currency,
            owner=self.user,
            visibility="private",
        )
        self.second_account = Account.objects.create(
            name="Savings",
            group=self.group,
            currency=self.currency,
            owner=self.user,
            visibility="private",
        )

        self.cat_transport = TransactionCategory.objects.create(
            name="Transport", owner=self.user, visibility="private"
        )
        self.cat_other = TransactionCategory.objects.create(
            name="Other", owner=self.user, visibility="private"
        )
        self.tag_commute = TransactionTag.objects.create(
            name="Commute", owner=self.user, visibility="private"
        )
        self.tag_rule = TransactionTag.objects.create(
            name="RuleApplied", owner=self.user, visibility="private"
        )
        self.entity_uber = TransactionEntity.objects.create(
            name="Uber", owner=self.user, visibility="private"
        )

        # Seed historical labeled transactions for Alice
        for day in (1, 5, 10):
            tx = Transaction.objects.create(
                owner=self.user,
                account=self.account,
                type=Transaction.Type.EXPENSE,
                date=datetime.date(2025, 1, day),
                amount=Decimal("25.00"),
                description=f"UBER *TRIP 0{day}/01",
                category=self.cat_transport,
            )
            tx.tags.add(self.tag_commute)
            tx.entities.add(self.entity_uber)

    def tearDown(self):
        if get_current_user() is not None:
            delete_current_user()

    def _tag_ids(self, tx: Transaction) -> list[int]:
        return list(
            Transaction.tags.through.objects.filter(transaction_id=tx.pk).values_list(
                "transactiontag_id", flat=True
            )
        )

    def _entity_ids(self, tx: Transaction) -> list[int]:
        return list(
            Transaction.entities.through.objects.filter(
                transaction_id=tx.pk
            ).values_list("transactionentity_id", flat=True)
        )

    def _create_unclassified_uber_tx(self, **overrides) -> Transaction:
        defaults = {
            "owner": self.user,
            "account": self.account,
            "type": Transaction.Type.EXPENSE,
            "date": datetime.date(2025, 2, 1),
            "amount": Decimal("27.00"),
            "description": "UBER *TRIP 01/02",
        }
        defaults.update(overrides)
        return Transaction.objects.create(**defaults)

    def test_auto_tags_unclassified_transaction_after_rules(self):
        tx = self._create_unclassified_uber_tx()

        check_for_transaction_rules(
            instance_id=tx.id,
            user_id=self.user.id,
            signal="transaction_created",
        )

        tx.refresh_from_db()
        self.assertEqual(tx.category_id, self.cat_transport.id)
        self.assertEqual(self._tag_ids(tx), [self.tag_commute.id])
        self.assertEqual(self._entity_ids(tx), [self.entity_uber.id])

    def test_skips_when_user_already_set_category_tag_or_entity(self):
        train_for_user(self.user)

        tx_with_cat = self._create_unclassified_uber_tx(category=self.cat_other)
        self.assertFalse(apply_auto_tagging(tx_with_cat, self.user))
        tx_with_cat.refresh_from_db()
        self.assertEqual(tx_with_cat.category_id, self.cat_other.id)
        self.assertEqual(self._tag_ids(tx_with_cat), [])
        self.assertEqual(self._entity_ids(tx_with_cat), [])

        tx_with_tag = self._create_unclassified_uber_tx()
        tx_with_tag.tags.add(self.tag_rule)
        self.assertFalse(apply_auto_tagging(tx_with_tag, self.user))
        tx_with_tag.refresh_from_db()
        self.assertIsNone(tx_with_tag.category_id)
        self.assertEqual(self._entity_ids(tx_with_tag), [])

        tx_with_entity = self._create_unclassified_uber_tx()
        tx_with_entity.entities.add(self.entity_uber)
        self.assertFalse(apply_auto_tagging(tx_with_entity, self.user))
        tx_with_entity.refresh_from_db()
        self.assertIsNone(tx_with_entity.category_id)
        self.assertEqual(self._tag_ids(tx_with_entity), [])

    def test_rules_run_before_auto_tagging_and_prevent_auto_tagging_if_rule_classifies(self):
        rule = TransactionRule.objects.create(
            owner=self.user,
            visibility="private",
            name="Tag Uber via Rule",
            trigger="'UBER' in description",
            on_create=True,
            active=True,
        )
        TransactionRuleAction.objects.create(
            rule=rule,
            field=TransactionRuleAction.Field.tags,
            value=f"['{self.tag_rule.name}']",
        )

        tx = self._create_unclassified_uber_tx()
        check_for_transaction_rules(
            instance_id=tx.id,
            user_id=self.user.id,
            signal="transaction_created",
        )

        tx.refresh_from_db()
        # Rule set the tag; auto-tagging should see the transaction is already classified and skip it
        self.assertEqual(self._tag_ids(tx), [self.tag_rule.id])
        self.assertIsNone(tx.category_id)
        self.assertEqual(self._entity_ids(tx), [])

    def test_user_settings_disable_auto_tagging(self):
        self.user.settings.auto_tagging = False
        self.user.settings.save()

        tx = self._create_unclassified_uber_tx()
        check_for_transaction_rules(
            instance_id=tx.id,
            user_id=self.user.id,
            signal="transaction_created",
        )

        tx.refresh_from_db()
        self.assertIsNone(tx.category_id)
        self.assertEqual(self._tag_ids(tx), [])
        self.assertEqual(self._entity_ids(tx), [])

    def test_per_item_auto_match_opt_out_and_inactive_items(self):
        train_for_user(self.user)

        self.cat_transport.auto_match = False
        self.cat_transport.save()
        self.tag_commute.active = False
        self.tag_commute.save()

        tx = self._create_unclassified_uber_tx()
        applied = apply_auto_tagging(tx, self.user)
        self.assertTrue(applied)

        tx.refresh_from_db()
        self.assertIsNone(tx.category_id)
        self.assertEqual(self._tag_ids(tx), [])
        self.assertEqual(self._entity_ids(tx), [self.entity_uber.id])

    def test_skips_transfers(self):
        train_for_user(self.user)

        tx_from = self._create_unclassified_uber_tx()
        tx_from.add_transfer_side(self.second_account, Decimal("27.00"))
        tx_from.refresh_from_db()

        self.assertFalse(apply_auto_tagging(tx_from, self.user))
        self.assertIsNone(tx_from.category_id)

    def test_multi_user_isolation(self):
        train_for_user(self.user)

        bob_group = AccountGroup.objects.create(name="Bob Group", owner=self.other_user)
        bob_account = Account.objects.create(
            name="Bob Card",
            group=bob_group,
            currency=self.currency,
            owner=self.other_user,
            visibility="private",
        )
        bob_tx = Transaction.objects.create(
            owner=self.other_user,
            account=bob_account,
            type=Transaction.Type.EXPENSE,
            date=datetime.date(2025, 2, 1),
            amount=Decimal("25.00"),
            description="UBER *TRIP 01/02",
        )

        self.assertFalse(apply_auto_tagging(bob_tx, self.other_user))
        bob_tx.refresh_from_db()
        self.assertIsNone(bob_tx.category_id)
        self.assertFalse(bob_tx.tags.exists())
        self.assertFalse(bob_tx.entities.exists())

    def test_procrastinate_training_tasks(self):
        msg = train_user_auto_tagger(self.user.id)
        self.assertIn("Trained auto-tagger", msg)
        model_obj = AutoTaggerModel.objects.get(user=self.user)
        self.assertEqual(model_obj.transaction_count, 3)

        # Periodic task skips already-up-to-date user
        with patch(
            "apps.transactions.tasks.train_for_user", wraps=train_for_user
        ) as mock_train:
            retrain_auto_taggers()
            trained_user_ids = [call.args[0].id for call in mock_train.call_args_list]
            self.assertNotIn(self.user.id, trained_user_ids)

    def test_retrain_auto_taggers_detects_shared_account_updates(self):
        # Train Bob initially (0 transactions visible)
        train_for_user(self.other_user)
        self.assertEqual(
            AutoTaggerModel.objects.get(user=self.other_user).transaction_count, 0
        )

        # Share Alice's account with Bob and add a new transaction owned by Alice
        self.account.shared_with.add(self.other_user)
        Transaction.objects.create(
            owner=self.user,
            account=self.account,
            type=Transaction.Type.EXPENSE,
            date=datetime.date(2025, 2, 2),
            amount=Decimal("30.00"),
            description="UBER *TRIP SHARED",
            category=self.cat_transport,
        )

        retrain_auto_taggers()

        bob_model = AutoTaggerModel.objects.get(user=self.other_user)
        self.assertGreater(bob_model.transaction_count, 0)

    def test_forms_expose_auto_tagging_and_auto_match_fields(self):
        write_current_user(self.user)
        settings_form = UserSettingsForm(instance=self.user.settings)
        self.assertIn("auto_tagging", settings_form.fields)

        cat_form = TransactionCategoryForm(instance=self.cat_transport)
        self.assertIn("auto_match", cat_form.fields)

        tag_form = TransactionTagForm(instance=self.tag_commute)
        self.assertIn("auto_match", tag_form.fields)

        entity_form = TransactionEntityForm(instance=self.entity_uber)
        self.assertIn("auto_match", entity_form.fields)
