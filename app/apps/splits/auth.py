from dataclasses import dataclass

from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.utils.crypto import constant_time_compare, salted_hmac
from django.http import Http404
from django.shortcuts import get_object_or_404

from apps.splits.models import SplitEvent, SplitParticipant

EXTERNAL_SESSION_KEY = "split_external_auth"


def _password_fingerprint(participant: SplitParticipant) -> str:
    # Binds the session to the current password, so a reset signs out old sessions
    return salted_hmac(
        "splits.external_session", participant.external_password_hash
    ).hexdigest()


@dataclass(frozen=True)
class SplitActor:
    event: SplitEvent
    participant: SplitParticipant | None
    user: object | None  # Django User or None for external participants
    is_external_portal: bool

    @property
    def is_creator(self) -> bool:
        return bool(
            not self.is_external_portal
            and self.user is not None
            and self.event.can_manage(self.user)
        )

    @property
    def is_wygiwyh_user(self) -> bool:
        return bool(not self.is_external_portal and self.user is not None)

    def can_record_payment(self, from_id: int | None, to_id: int | None) -> bool:
        # Only the two people involved (or the organizer) can say money changed hands
        if self.is_creator:
            return True
        return bool(self.participant and self.participant.id in (from_id, to_id))

    def can_edit_item(self, *, created_by_id: int | None, primary_participant_id: int | None) -> bool:
        if self.is_creator:
            return True
        if not self.participant or not self.participant.is_active:
            return False
        return self.participant.id in {created_by_id, primary_participant_id}


def user_display_name(user) -> str:
    full = f"{user.first_name} {user.last_name}".strip()
    return full or user.email


def accessible_events(user):
    """Events a WYGIWYH user organizes or actively takes part in."""
    return SplitEvent.objects.filter(
        Q(creator=user) | Q(participants__user=user, participants__is_active=True)
    ).distinct()


def wygiwyh_actor_for(event: SplitEvent, user) -> SplitActor:
    return SplitActor(
        event=event,
        participant=event.get_wygiwyh_participant(user),
        user=user,
        is_external_portal=False,
    )


def set_external_session(request, event: SplitEvent, participant: SplitParticipant):
    auth_map = dict(request.session.get(EXTERNAL_SESSION_KEY, {}))
    auth_map[str(event.id)] = {
        "participant_id": participant.id,
        "share_token": str(event.share_token),
        "password": _password_fingerprint(participant),
    }
    request.session[EXTERNAL_SESSION_KEY] = auth_map
    request.session.modified = True


def clear_external_session(request, event: SplitEvent):
    auth_map = dict(request.session.get(EXTERNAL_SESSION_KEY, {}))
    if str(event.id) in auth_map:
        del auth_map[str(event.id)]
        request.session[EXTERNAL_SESSION_KEY] = auth_map
        request.session.modified = True


def get_external_participant_from_session(
    request, event: SplitEvent
) -> SplitParticipant | None:
    if not event.allow_external_access:
        return None
    auth_map = request.session.get(EXTERNAL_SESSION_KEY, {})
    entry = auth_map.get(str(event.id))
    if not isinstance(entry, dict):
        return None
    if entry.get("share_token") != str(event.share_token):
        return None
    participant_id = entry.get("participant_id")
    if not participant_id:
        return None
    participant = (
        SplitParticipant.objects.filter(
            id=participant_id,
            event=event,
            is_external=True,
            is_active=True,
        )
        .exclude(external_password_hash="")
        .first()
    )
    if participant and constant_time_compare(
        entry.get("password", ""), _password_fingerprint(participant)
    ):
        return participant
    return None


def get_wygiwyh_actor(request, event_id: int) -> SplitActor:
    if not request.user.is_authenticated:
        raise PermissionDenied
    event = get_object_or_404(
        SplitEvent.objects.select_related("currency", "creator"),
        id=event_id,
    )
    if not event.is_accessible_by_user(request.user):
        raise Http404
    participant = event.get_wygiwyh_participant(request.user)
    return SplitActor(
        event=event,
        participant=participant,
        user=request.user,
        is_external_portal=False,
    )


def get_external_actor(request, share_token) -> SplitActor | None:
    event = get_object_or_404(
        SplitEvent.objects.select_related("currency", "creator"),
        share_token=share_token,
    )
    if not event.allow_external_access:
        raise Http404
    participant = get_external_participant_from_session(request, event)
    if not participant:
        return None
    return SplitActor(
        event=event,
        participant=participant,
        user=None,
        is_external_portal=True,
    )
