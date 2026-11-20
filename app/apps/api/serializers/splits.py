from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction as db_transaction
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from apps.splits.auth import accessible_events, user_display_name, wygiwyh_actor_for
from apps.splits.models import (
    SplitEvent,
    SplitExpense,
    SplitExpenseShare,
    SplitParticipant,
    SplitPayment,
)
from apps.splits.services.splitting import compute_expense_shares, replace_expense_shares
from apps.splits.services.wygiwyh_sync import settle_pending_links_for_payment

User = get_user_model()


class AccessibleEventField(serializers.PrimaryKeyRelatedField):
    def get_queryset(self):
        return accessible_events(self.context["request"].user)


class EventParticipantField(serializers.PrimaryKeyRelatedField):
    """A participant id; checked against the event in the serializer's validate()."""

    def get_queryset(self):
        return SplitParticipant.objects.filter(
            event__in=accessible_events(self.context["request"].user)
        )


def _check_participants(event, participants, allowed_inactive=()):
    for p in participants:
        if p.event_id != event.id:
            raise serializers.ValidationError(
                _("%(name)s is not part of this event.") % {"name": p.name}
            )
        if not p.is_active and p.id not in allowed_inactive:
            raise serializers.ValidationError(
                _("%(name)s is inactive.") % {"name": p.name}
            )


class SplitParticipantSerializer(serializers.ModelSerializer):
    event = AccessibleEventField()
    user = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(is_active=True),
        required=False,
        allow_null=True,
        help_text="A WYGIWYH user to add. Leave empty to add a person without an account (give `name`).",
    )
    name = serializers.CharField(
        max_length=150,
        required=False,
        help_text="Required for people without an account; defaults to the user's name.",
    )
    is_claimed = serializers.BooleanField(
        read_only=True,
        help_text="For people without an account: whether they set a password through the share link.",
    )
    is_creator = serializers.BooleanField(read_only=True)

    class Meta:
        model = SplitParticipant
        fields = [
            "id",
            "event",
            "name",
            "user",
            "is_external",
            "is_active",
            "is_claimed",
            "is_creator",
            "created_at",
        ]
        read_only_fields = ["is_external", "created_at"]
        # validate() checks the unique user/name rules with clearer messages, and
        # DRF's auto validators would make `name` required when adding a user
        validators = []

    def validate(self, attrs):
        if self.instance:
            # Who a participant is can't change; only name and is_active
            for field in ("event", "user"):
                if field in attrs and attrs[field] != getattr(self.instance, field):
                    raise serializers.ValidationError({field: _("Can't be changed.")})
            if attrs.get("is_active") is False and self.instance.is_creator:
                raise serializers.ValidationError(
                    {"is_active": _("The event creator cannot be deactivated.")}
                )
            name = attrs.get("name")
            event = self.instance.event
        else:
            event = attrs["event"]
            user = attrs.get("user")
            if user:
                if event.participants.filter(user=user).exists():
                    raise serializers.ValidationError({"user": _("Already in this event.")})
                attrs.setdefault("name", user_display_name(user))
                attrs["is_external"] = False
            elif not attrs.get("name", "").strip():
                raise serializers.ValidationError({"name": _("This field is required.")})
            else:
                attrs["is_external"] = True
            name = attrs["name"] = attrs["name"].strip()

        if name:
            clash = event.participants.filter(name__iexact=name)
            if self.instance:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise serializers.ValidationError(
                    {"name": _("A participant named '%(name)s' already exists in this event.") % {"name": name}}
                )
        return attrs


class SplitEventSerializer(serializers.ModelSerializer):
    participants = SplitParticipantSerializer(many=True, read_only=True)
    is_organizer = serializers.SerializerMethodField()
    share_url = serializers.SerializerMethodField(
        help_text="Link for people without an account. Only shown to the organizer, and only while external access is on."
    )

    class Meta:
        model = SplitEvent
        fields = [
            "id",
            "name",
            "description",
            "currency",
            "allow_external_access",
            "is_archived",
            "is_organizer",
            "share_url",
            "participants",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_is_organizer(self, obj) -> bool:
        return obj.creator_id == self.context["request"].user.id

    def get_share_url(self, obj) -> str | None:
        if not (self.get_is_organizer(obj) and obj.allow_external_access):
            return None
        return self.context["request"].build_absolute_uri(
            reverse("split_external_auth", kwargs={"share_token": obj.share_token})
        )

    def validate_currency(self, value):
        event = self.instance
        if (
            event
            and value != event.currency
            and (event.expenses.exists() or event.payments.exists())
        ):
            # Stored amounts are not converted
            raise serializers.ValidationError(
                _("The currency can't be changed after expenses or payments are added.")
            )
        return value

    @db_transaction.atomic
    def create(self, validated_data):
        user = self.context["request"].user
        event = SplitEvent.objects.create(creator=user, **validated_data)
        SplitParticipant.objects.create(
            event=event, user=user, name=user_display_name(user), is_external=False
        )
        return event


class SplitShareInputSerializer(serializers.Serializer):
    participant = serializers.IntegerField()
    value = serializers.DecimalField(
        max_digits=20,
        decimal_places=6,
        required=False,
        help_text="Ignored for EQUAL. The exact amount for EXACT, the percentage (0-100) for PERCENTAGE, the weight for SHARES.",
    )


class SplitExpenseShareSerializer(serializers.ModelSerializer):
    class Meta:
        model = SplitExpenseShare
        fields = ["participant", "amount", "percentage", "shares"]


class SplitExpenseSerializer(serializers.ModelSerializer):
    event = AccessibleEventField()
    paid_by = EventParticipantField()
    shares = SplitExpenseShareSerializer(many=True, read_only=True)
    split_between = SplitShareInputSerializer(
        many=True,
        write_only=True,
        required=False,
        help_text=(
            "Who shares the cost. On create, omit it to split equally between every active participant. "
            "On update, omit it to keep the current people and values."
        ),
    )

    class Meta:
        model = SplitExpense
        fields = [
            "id",
            "event",
            "description",
            "amount",
            "date",
            "paid_by",
            "split_type",
            "split_between",
            "shares",
            "notes",
            "created_by_participant",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_by_participant", "created_at", "updated_at"]

    def validate(self, attrs):
        instance = self.instance
        event = attrs.get("event") or instance.event
        if instance and event != instance.event:
            raise serializers.ValidationError({"event": _("Can't be changed.")})

        # People already on the expense may have been deactivated since
        existing_ids = (
            set(instance.shares.values_list("participant_id", flat=True)) | {instance.paid_by_id}
            if instance
            else set()
        )
        paid_by = attrs.get("paid_by") or instance.paid_by
        _check_participants(event, [paid_by], existing_ids)

        split_type = attrs.get("split_type") or (
            instance.split_type if instance else SplitExpense.SplitType.EQUAL
        )
        split_between = attrs.pop("split_between", None)
        if split_between is None:
            if not instance:
                if split_type != SplitExpense.SplitType.EQUAL:
                    raise serializers.ValidationError(
                        {"split_between": _("Required unless split_type is EQUAL.")}
                    )
                split_between = [
                    {"participant": p.id} for p in event.participants.filter(is_active=True)
                ]
            elif split_type != instance.split_type and split_type != SplitExpense.SplitType.EQUAL:
                raise serializers.ValidationError(
                    {"split_between": _("Required when changing split_type.")}
                )
            else:
                field = {
                    SplitExpense.SplitType.EXACT: "amount",
                    SplitExpense.SplitType.PERCENTAGE: "percentage",
                    SplitExpense.SplitType.SHARES: "shares",
                }.get(split_type)
                split_between = [
                    {"participant": s.participant_id, "value": getattr(s, field) if field else None}
                    for s in instance.shares.all()
                ]

        by_id = {p.id: p for p in event.participants.all()}
        participants, values = [], {}
        for row in split_between:
            p = by_id.get(row["participant"])
            if p is None:
                raise serializers.ValidationError(
                    {"split_between": _("Participant %(id)s is not part of this event.") % {"id": row["participant"]}}
                )
            participants.append(p)
            if row.get("value") is not None:
                values[p.id] = row["value"]
        try:
            _check_participants(event, participants, existing_ids)
            self._computed_shares = compute_expense_shares(
                total_amount=attrs.get("amount") or instance.amount,
                split_type=split_type,
                participants=participants,
                decimal_places=event.currency.decimal_places,
                values_by_participant_id=values,
            )
        except DjangoValidationError as e:
            raise serializers.ValidationError({"split_between": e.messages})
        return attrs

    @db_transaction.atomic
    def save(self, **kwargs):
        expense = super().save(**kwargs)
        replace_expense_shares(expense, self._computed_shares)
        return expense


class SplitPaymentSerializer(serializers.ModelSerializer):
    event = AccessibleEventField()
    from_participant = EventParticipantField()
    to_participant = EventParticipantField()

    class Meta:
        model = SplitPayment
        fields = [
            "id",
            "event",
            "from_participant",
            "to_participant",
            "amount",
            "date",
            "notes",
            "created_by_participant",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_by_participant", "created_at", "updated_at"]

    def validate(self, attrs):
        instance = self.instance
        event = attrs.get("event") or instance.event
        if instance and event != instance.event:
            raise serializers.ValidationError({"event": _("Can't be changed.")})
        from_p = attrs.get("from_participant") or instance.from_participant
        to_p = attrs.get("to_participant") or instance.to_participant
        existing = {instance.from_participant_id, instance.to_participant_id} if instance else set()
        _check_participants(event, [from_p, to_p], existing)
        if from_p == to_p:
            raise serializers.ValidationError(
                {"to_participant": _("Sender and recipient must be different participants.")}
            )
        actor = wygiwyh_actor_for(event, self.context["request"].user)
        if not actor.can_record_payment(from_p.id, to_p.id):
            raise serializers.ValidationError(
                _("You can only record payments you sent or received.")
            )
        return attrs

    @db_transaction.atomic
    def create(self, validated_data):
        payment = super().create(validated_data)
        # Marks the payer's and receiver's planned transactions as paid, as the web UI does
        settle_pending_links_for_payment(payment)
        return payment


class SplitBalanceSerializer(serializers.Serializer):
    participant = serializers.IntegerField()
    name = serializers.CharField()
    is_active = serializers.BooleanField()
    paid = serializers.DecimalField(max_digits=20, decimal_places=6, help_text="Expenses they paid for.")
    share = serializers.DecimalField(max_digits=20, decimal_places=6, help_text="Their part of all expenses.")
    sent = serializers.DecimalField(max_digits=20, decimal_places=6, help_text="Payments they made.")
    received = serializers.DecimalField(max_digits=20, decimal_places=6, help_text="Payments they got.")
    balance = serializers.DecimalField(
        max_digits=20, decimal_places=6, help_text="Above 0: others owe them. Below 0: they owe."
    )


class SplitTransferSerializer(serializers.Serializer):
    from_participant = serializers.IntegerField()
    from_name = serializers.CharField()
    to_participant = serializers.IntegerField()
    to_name = serializers.CharField()
    amount = serializers.DecimalField(max_digits=20, decimal_places=6)


class SplitSummarySerializer(serializers.Serializer):
    currency = serializers.CharField()
    total_spent = serializers.DecimalField(max_digits=20, decimal_places=6)
    balances = SplitBalanceSerializer(many=True)
    settle_up = SplitTransferSerializer(
        many=True, help_text="The fewest payments that settle everyone up."
    )
