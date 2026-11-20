from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.api.serializers.splits import (
    SplitEventSerializer,
    SplitExpenseSerializer,
    SplitParticipantSerializer,
    SplitPaymentSerializer,
    SplitSummarySerializer,
)
from apps.splits.auth import accessible_events, wygiwyh_actor_for
from apps.splits.models import SplitEvent, SplitExpense, SplitParticipant, SplitPayment
from apps.splits.services.membership import leave_event
from apps.splits.services.settlement import get_event_settlement_summary


class SplitsQuerysetMixin:
    """Scopes every queryset to events the user can see."""

    def get_queryset(self):
        # drf-spectacular builds the schema without a user
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        return self.scoped_queryset(accessible_events(self.request.user))


def _require_organizer(event, user):
    if event.creator_id != user.id:
        raise PermissionDenied(_("Only the event organizer can do this."))


class SplitEventViewSet(SplitsQuerysetMixin, viewsets.ModelViewSet):
    """Shared-expense events (trips, flats, dinners) you organize or take part in.

    Only the organizer can edit or delete an event. Creating one makes you its
    organizer and first participant."""

    serializer_class = SplitEventSerializer
    filterset_fields = {
        "name": ["exact", "icontains"],
        "is_archived": ["exact"],
        "currency": ["exact"],
    }
    ordering_fields = ["name", "created_at", "updated_at"]

    queryset = SplitEvent.objects.none()

    def scoped_queryset(self, events):
        return (
            events
            .select_related("currency")
            .prefetch_related("participants__event")
            .order_by("-created_at")
        )

    def perform_update(self, serializer):
        _require_organizer(serializer.instance, self.request.user)
        serializer.save()

    def perform_destroy(self, instance):
        _require_organizer(instance, self.request.user)
        instance.delete()

    @extend_schema(
        summary="Balances and how to settle up",
        description=(
            "Each person's totals and net balance, and the fewest payments that settle "
            "everyone up. Amounts are in the event's currency."
        ),
        responses=SplitSummarySerializer,
    )
    @action(detail=True, methods=["get"])
    def summary(self, request, pk=None):
        event = self.get_object()
        summary = get_event_settlement_summary(event)
        return Response(
            SplitSummarySerializer(
                {
                    "currency": event.currency.code,
                    "total_spent": summary["total_spent"],
                    "balances": [
                        {
                            "participant": b.participant.id,
                            "name": b.participant.name,
                            "is_active": b.participant.is_active,
                            "paid": b.total_paid,
                            "share": b.total_owed,
                            "sent": b.payments_sent,
                            "received": b.payments_received,
                            "balance": b.net_balance,
                        }
                        for b in summary["balances"]
                    ],
                    "settle_up": [
                        {
                            "from_participant": t.from_participant.id,
                            "from_name": t.from_participant.name,
                            "to_participant": t.to_participant.id,
                            "to_name": t.to_participant.name,
                            "amount": t.amount,
                        }
                        for t in summary["transfers"]
                    ],
                }
            ).data
        )

    @extend_schema(
        summary="Leave an event",
        description=(
            "Removes you from an event someone else organizes. If you have expenses or "
            "payments you're deactivated instead, so everyone else's balances stay right. "
            "The organizer can't leave."
        ),
        request=None,
        responses={204: None},
    )
    @action(detail=True, methods=["post"])
    def leave(self, request, pk=None):
        event = self.get_object()
        actor = wygiwyh_actor_for(event, request.user)
        if actor.is_creator or not actor.participant:
            raise PermissionDenied(_("The organizer can't leave their own event."))
        leave_event(actor)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SplitParticipantViewSet(SplitsQuerysetMixin, viewsets.ModelViewSet):
    """People in an event: WYGIWYH users (`user` set) or people without an account.

    Only the organizer can add, rename, deactivate (`is_active: false`) or remove
    people. Someone with expenses or payments can't be removed, only deactivated."""

    serializer_class = SplitParticipantSerializer
    filterset_fields = {"event": ["exact"], "is_active": ["exact"], "is_external": ["exact"]}

    queryset = SplitParticipant.objects.none()

    def scoped_queryset(self, events):
        return SplitParticipant.objects.filter(event__in=events).select_related("event")

    def perform_create(self, serializer):
        _require_organizer(serializer.validated_data["event"], self.request.user)
        serializer.save()

    def perform_update(self, serializer):
        _require_organizer(serializer.instance.event, self.request.user)
        serializer.save()

    def perform_destroy(self, instance):
        _require_organizer(instance.event, self.request.user)
        if not instance.can_be_deleted():
            raise ValidationError(
                _("%(name)s has expenses or payments and can't be removed. Deactivate them instead.")
                % {"name": instance.name}
            )
        instance.delete()


def _require_item_editor(event, user, *, created_by_id, primary_participant_id):
    actor = wygiwyh_actor_for(event, user)
    if not actor.can_edit_item(
        created_by_id=created_by_id, primary_participant_id=primary_participant_id
    ):
        raise PermissionDenied(
            _("Only the organizer, whoever added it, or whoever paid can change this.")
        )
    return actor


class SplitExpenseViewSet(SplitsQuerysetMixin, viewsets.ModelViewSet):
    """Expenses in an event and how each one is split.

    Shares are computed from `split_type` and `split_between` and always add up to
    the amount. Anyone in the event can add expenses; the organizer, whoever added
    it, or whoever paid can change or delete one."""

    serializer_class = SplitExpenseSerializer
    filterset_fields = {
        "event": ["exact"],
        "paid_by": ["exact"],
        "split_type": ["exact"],
        "date": ["exact", "gte", "lte", "gt", "lt"],
        "description": ["exact", "icontains"],
    }
    ordering_fields = ["date", "amount", "created_at"]

    queryset = SplitExpense.objects.none()

    def scoped_queryset(self, events):
        return (
            SplitExpense.objects.filter(event__in=events)
            .select_related("event__currency")
            .prefetch_related("shares")
        )

    def perform_create(self, serializer):
        actor = wygiwyh_actor_for(serializer.validated_data["event"], self.request.user)
        serializer.save(created_by_participant=actor.participant)

    def perform_update(self, serializer):
        e = serializer.instance
        _require_item_editor(
            e.event, self.request.user, created_by_id=e.created_by_participant_id, primary_participant_id=e.paid_by_id
        )
        serializer.save()

    def perform_destroy(self, instance):
        _require_item_editor(
            instance.event,
            self.request.user,
            created_by_id=instance.created_by_participant_id,
            primary_participant_id=instance.paid_by_id,
        )
        for attachment in instance.attachments.all():
            attachment.file.delete(save=False)
        instance.delete()


class SplitPaymentViewSet(SplitsQuerysetMixin, viewsets.ModelViewSet):
    """Money that changed hands between two people in an event.

    Only the two people involved or the organizer can record one. Recording a
    payment marks matching planned transactions in their accounts as paid."""

    serializer_class = SplitPaymentSerializer
    filterset_fields = {
        "event": ["exact"],
        "from_participant": ["exact"],
        "to_participant": ["exact"],
        "date": ["exact", "gte", "lte", "gt", "lt"],
    }
    ordering_fields = ["date", "amount", "created_at"]

    queryset = SplitPayment.objects.none()

    def scoped_queryset(self, events):
        return SplitPayment.objects.filter(event__in=events).select_related("event")

    def perform_create(self, serializer):
        actor = wygiwyh_actor_for(serializer.validated_data["event"], self.request.user)
        serializer.save(created_by_participant=actor.participant)

    def perform_update(self, serializer):
        p = serializer.instance
        _require_item_editor(
            p.event, self.request.user, created_by_id=p.created_by_participant_id, primary_participant_id=p.from_participant_id
        )
        serializer.save()

    def perform_destroy(self, instance):
        _require_item_editor(
            instance.event,
            self.request.user,
            created_by_id=instance.created_by_participant_id,
            primary_participant_id=instance.from_participant_id,
        )
        for attachment in instance.attachments.all():
            attachment.file.delete(save=False)
        instance.delete()
