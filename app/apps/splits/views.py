from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction as db_transaction
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from apps.common.decorators.htmx import only_htmx
from apps.splits.auth import (
    SplitActor,
    accessible_events,
    user_display_name,
    clear_external_session,
    get_external_actor,
    get_external_participant_from_session,
    get_wygiwyh_actor,
    set_external_session,
)
from apps.splits.forms import (
    AddExternalParticipantForm,
    AddWygiwyhParticipantForm,
    ExternalAuthForm,
    SplitEventForm,
    SplitExpenseForm,
    SplitPaymentForm,
    SplitTransactionSyncForm,
)
from apps.splits.models import (
    SplitAttachment,
    SplitEvent,
    SplitExpense,
    SplitParticipant,
    SplitPayment,
    SplitTransactionLink,
)
from apps.splits.services.settlement import get_event_settlement_summary
from apps.splits.services.membership import leave_event
from apps.splits.services.splitting import replace_expense_shares
from apps.splits.services.wygiwyh_sync import (
    build_default_sync_description,
    create_and_link_transaction,
    expected_transaction_type_for_kind,
    link_existing_transaction,
    settle_pending_links_for_payment,
)


def _portal_urls(actor: SplitActor) -> dict:
    event = actor.event
    if actor.is_external_portal:
        tok = event.share_token
        return {
            "event_detail": reverse("split_external_event_detail", kwargs={"share_token": tok}),
            "event_content": reverse("split_external_event_content", kwargs={"share_token": tok}),
            "report": reverse("split_external_event_report", kwargs={"share_token": tok}),
            "expense_add": reverse("split_external_expense_add", kwargs={"share_token": tok}),
            "payment_add": reverse("split_external_payment_add", kwargs={"share_token": tok}),
            "expense_edit_name": "split_external_expense_edit",
            "expense_delete_name": "split_external_expense_delete",
            "payment_edit_name": "split_external_payment_edit",
            "payment_delete_name": "split_external_payment_delete",
            "attachment_download_name": "split_external_attachment_download",
            "attachment_delete_name": "split_external_attachment_delete",
            "url_kwarg_key": "share_token",
            "url_kwarg_val": tok,
        }
    return {
        "event_detail": reverse("split_event_detail", kwargs={"event_id": event.id}),
        "event_content": reverse("split_event_content", kwargs={"event_id": event.id}),
        "report": reverse("split_event_report", kwargs={"event_id": event.id}),
        "expense_add": reverse("split_expense_add", kwargs={"event_id": event.id}),
        "payment_add": reverse("split_payment_add", kwargs={"event_id": event.id}),
        "expense_edit_name": "split_expense_edit",
        "expense_delete_name": "split_expense_delete",
        "payment_edit_name": "split_payment_edit",
        "payment_delete_name": "split_payment_delete",
        "attachment_download_name": "split_attachment_download",
        "attachment_delete_name": "split_attachment_delete",
        "url_kwarg_key": "event_id",
        "url_kwarg_val": event.id,
    }


def _build_event_context(request, actor: SplitActor) -> dict:
    event = actor.event
    summary = get_event_settlement_summary(event)

    expenses = list(
        event.expenses.select_related("paid_by", "created_by_participant")
        .prefetch_related("shares__participant", "attachments")
        .all()
    )
    payments = list(
        event.payments.select_related(
            "from_participant", "to_participant", "created_by_participant"
        )
        .prefetch_related("attachments")
        .all()
    )

    # Map WYGIWYH transaction links for the current logged-in WYGIWYH user
    expense_links: dict[int, list[SplitTransactionLink]] = {}
    payment_links: dict[int, list[SplitTransactionLink]] = {}
    settlement_out_links: dict[int, list[SplitTransactionLink]] = {}
    settlement_in_links: dict[int, list[SplitTransactionLink]] = {}

    if actor.is_wygiwyh_user:
        user_links = (
            SplitTransactionLink.objects.filter(
                event=event,
                user=actor.user,
                transaction__deleted=False,
            )
            .select_related("transaction", "transaction__account", "transaction__account__currency", "counterparty")
            .all()
        )
        for link in user_links:
            if link.expense_id:
                expense_links.setdefault(link.expense_id, []).append(link)
            elif link.payment_id:
                payment_links.setdefault(link.payment_id, []).append(link)
            elif link.kind == SplitTransactionLink.Kind.SETTLEMENT_OUT and link.counterparty_id:
                settlement_out_links.setdefault(link.counterparty_id, []).append(link)
            elif link.kind == SplitTransactionLink.Kind.SETTLEMENT_IN and link.counterparty_id:
                settlement_in_links.setdefault(link.counterparty_id, []).append(link)

    me_id = actor.participant.id if actor.participant else None
    # Only money that moved through the user's own accounts can be synced (matches sync views)
    sync_id = me_id if actor.is_wygiwyh_user else None

    for exp in expenses:
        exp.can_edit = actor.can_edit_item(
            created_by_id=exp.created_by_participant_id,
            primary_participant_id=exp.paid_by_id,
        )
        exp.can_sync = sync_id is not None and exp.paid_by_id == sync_id
        exp.user_tx_links = expense_links.get(exp.id, [])
        # What this expense means for the viewer: > 0 lent, < 0 borrowed, None not involved
        my_share = next((s.amount for s in exp.shares.all() if s.participant_id == me_id), None)
        if exp.paid_by_id == me_id:
            exp.my_delta = exp.amount - (my_share or 0)
        else:
            exp.my_delta = -my_share if my_share is not None else None
        exp.my_delta_abs = abs(exp.my_delta) if exp.my_delta is not None else None

    for pay in payments:
        pay.is_payment = True
        pay.can_edit = actor.can_edit_item(
            created_by_id=pay.created_by_participant_id,
            primary_participant_id=pay.from_participant_id,
        )
        pay.can_sync = sync_id is not None and sync_id in (
            pay.from_participant_id,
            pay.to_participant_id,
        )
        pay.user_tx_links = payment_links.get(pay.id, [])

    activity = sorted(
        [*expenses, *payments], key=lambda i: (i.date, i.created_at), reverse=True
    )

    # Diverging bar per person, scaled to the largest balance
    max_abs = max((abs(b.net_balance) for b in summary["balances"]), default=0)
    balance_rows = [
        {
            "balance": b,
            "bar": int(abs(b.net_balance) * 50 / max_abs) if max_abs else 0,
        }
        for b in summary["balances"]
    ]

    enriched_transfers = []
    for t in summary["transfers"]:
        user_direction = None
        counterparty = None
        links = []
        if actor.is_wygiwyh_user and actor.participant:
            if t.from_participant.id == actor.participant.id:
                user_direction = "out"
                counterparty = t.to_participant
                links = settlement_out_links.get(counterparty.id, [])
            elif t.to_participant.id == actor.participant.id:
                user_direction = "in"
                counterparty = t.from_participant
                links = settlement_in_links.get(counterparty.id, [])
        enriched_transfers.append(
            {
                "transfer": t,
                "user_direction": user_direction,
                "counterparty": counterparty,
                "tx_links": links,
                "can_record": actor.can_record_payment(
                    t.from_participant.id, t.to_participant.id
                ),
            }
        )

    my_balance = (
        summary["balances_by_id"].get(actor.participant.id)
        if actor.participant
        else None
    )

    share_url = request.build_absolute_uri(
        reverse("split_external_auth", kwargs={"share_token": event.share_token})
    )

    active_participants_count = sum(
        1 for b in summary["balances"] if b.participant.is_active
    )

    return {
        "event": event,
        "actor": actor,
        "urls": _portal_urls(actor),
        "balance_rows": balance_rows,
        "transfers": enriched_transfers,
        "total_spent": summary["total_spent"],
        "my_balance": my_balance,
        "my_balance_abs": abs(my_balance.net_balance) if my_balance else None,
        "me_id": me_id,
        "active_participants_count": active_participants_count,
        "activity": activity,
        "expense_count": len(expenses),
        "payment_count": len(payments),
        "share_url": share_url,
    }


def _save_expense_from_form(
    form: SplitExpenseForm,
    *,
    actor: SplitActor,
    files,
) -> SplitExpense:
    with db_transaction.atomic():
        expense: SplitExpense = form.save(commit=False)
        expense.event = actor.event
        if not expense.pk:
            expense.created_by_participant = actor.participant
        expense.save()

        replace_expense_shares(expense, form.computed_shares)

        for f in files:
            SplitAttachment.objects.create(
                event=actor.event,
                expense=expense,
                file=f,
                original_name=f.name,
                content_type=getattr(f, "content_type", ""),
                size=f.size,
                uploaded_by=actor.participant,
            )
    return expense


def _save_payment_from_form(
    form: SplitPaymentForm,
    *,
    actor: SplitActor,
    files,
) -> SplitPayment:
    is_new = not form.instance.pk
    with db_transaction.atomic():
        payment: SplitPayment = form.save(commit=False)
        payment.event = actor.event
        if is_new:
            payment.created_by_participant = actor.participant
        payment.save()

        for f in files:
            SplitAttachment.objects.create(
                event=actor.event,
                payment=payment,
                file=f,
                original_name=f.name,
                content_type=getattr(f, "content_type", ""),
                size=f.size,
                uploaded_by=actor.participant,
            )

        if is_new:
            settle_pending_links_for_payment(payment)
    return payment


def _build_expense_form_context(
    form: SplitExpenseForm,
    actor: SplitActor,
    *,
    expense: SplitExpense | None = None,
    post_url: str,
) -> dict:
    # Build per-participant initial state for the share selector UI
    if form.is_bound:
        selected_ids = set()
        for raw in form.data.getlist("share_participants"):
            try:
                selected_ids.add(int(raw))
            except (TypeError, ValueError):
                pass
        rows = []
        for p in form.available_participants:
            rows.append(
                {
                    "participant": p,
                    "selected": p.id in selected_ids,
                    "value": form.data.get(f"share_value_{p.id}", ""),
                }
            )
    elif expense and expense.pk:
        share_map = {s.participant_id: s for s in expense.shares.all()}
        rows = []
        for p in form.available_participants:
            s = share_map.get(p.id)
            val = ""
            if s:
                if expense.split_type == SplitExpense.SplitType.EXACT:
                    val = f"{s.amount.normalize():f}"
                elif expense.split_type == SplitExpense.SplitType.PERCENTAGE and s.percentage is not None:
                    val = f"{s.percentage.normalize():f}"
                elif expense.split_type == SplitExpense.SplitType.SHARES and s.shares is not None:
                    val = f"{s.shares.normalize():f}"
            rows.append(
                {
                    "participant": p,
                    "selected": s is not None,
                    "value": val,
                }
            )
    else:
        rows = [
            {
                "participant": p,
                "selected": True,
                "value": "",
            }
            for p in form.available_participants
        ]

    return {
        "form": form,
        "event": actor.event,
        "actor": actor,
        "expense": expense,
        "participant_rows": rows,
        "post_url": post_url,
        "urls": _portal_urls(actor),
    }


# =============================================================================
# WYGIWYH User Views
# =============================================================================


@login_required
def event_index(request):
    return render(request, "splits/pages/event_index.html")


@only_htmx
@login_required
def event_list(request):
    show_archived = request.GET.get("archived") == "1"
    events_qs = (
        accessible_events(request.user)
        .select_related("currency", "creator")
        .prefetch_related("participants")
    )
    if not show_archived:
        events_qs = events_qs.filter(is_archived=False)

    event_cards = []
    for event in events_qs:
        summary = get_event_settlement_summary(event)
        me = event.get_wygiwyh_participant(request.user)
        my_bal = summary["balances_by_id"].get(me.id) if me else None
        event_cards.append(
            {
                "event": event,
                "total_spent": summary["total_spent"],
                "my_balance": my_bal,
                "participant_count": sum(
                    1 for p in event.participants.all() if p.is_active
                ),
                "is_creator": event.can_manage(request.user),
            }
        )

    return render(
        request,
        "splits/fragments/event/list.html",
        {
            "event_cards": event_cards,
            "show_archived": show_archived,
        },
    )


@only_htmx
@login_required
def event_add(request):
    if request.method == "POST":
        form = SplitEventForm(request.POST)
        if form.is_valid():
            with db_transaction.atomic():
                event = form.save(commit=False)
                event.creator = request.user
                event.save()
                SplitParticipant.objects.create(
                    event=event,
                    user=request.user,
                    name=user_display_name(request.user),
                    is_external=False,
                    is_active=True,
                )
            messages.success(request, _("Split event created successfully"))
            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "updated, hide_offcanvas"},
            )
    else:
        form = SplitEventForm()

    return render(request, "splits/fragments/event/add.html", {"form": form})


@login_required
def event_detail(request, event_id):
    actor = get_wygiwyh_actor(request, event_id)
    return render(
        request,
        "splits/pages/event_detail.html",
        {
            "event": actor.event,
            "actor": actor,
            "urls": _portal_urls(actor),
        },
    )


@only_htmx
@login_required
def event_content(request, event_id):
    actor = get_wygiwyh_actor(request, event_id)
    ctx = _build_event_context(request, actor)
    return render(request, "splits/fragments/event/content.html", ctx)


@login_required
def event_report(request, event_id):
    actor = get_wygiwyh_actor(request, event_id)
    return render(
        request, "splits/pages/event_report.html", _build_event_context(request, actor)
    )


@only_htmx
@login_required
def event_edit(request, event_id):
    actor = get_wygiwyh_actor(request, event_id)
    if not actor.is_creator:
        raise PermissionDenied

    if request.method == "POST":
        form = SplitEventForm(request.POST, instance=actor.event)
        if form.is_valid():
            form.save()
            messages.success(request, _("Event updated successfully"))
            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "updated, hide_offcanvas"},
            )
    else:
        form = SplitEventForm(instance=actor.event)

    return render(
        request,
        "splits/fragments/event/edit.html",
        {"form": form, "event": actor.event},
    )


@only_htmx
@login_required
@require_http_methods(["DELETE"])
def event_delete(request, event_id):
    actor = get_wygiwyh_actor(request, event_id)
    if not actor.is_creator:
        raise PermissionDenied
    actor.event.delete()
    messages.success(request, _("Event deleted successfully"))
    return HttpResponse(
        status=204,
        headers={
            "HX-Redirect": reverse("split_event_index"),
        },
    )


@only_htmx
@login_required
@require_http_methods(["POST"])
def event_leave(request, event_id):
    actor = get_wygiwyh_actor(request, event_id)
    if actor.is_creator or not actor.participant:
        raise PermissionDenied

    leave_event(actor)

    messages.success(request, _("You left %(name)s") % {"name": actor.event.name})
    return HttpResponse(
        status=204,
        headers={"HX-Redirect": reverse("split_event_index")},
    )


# =============================================================================
# Participants & Share Link Management (Creator only)
# =============================================================================


def _render_participants_manage(request, actor: SplitActor, wygiwyh_form=None, external_form=None):
    event = actor.event
    participants = list(event.participants.select_related("user").all())
    for p in participants:
        p.has_contribs = p.has_contributions()
        p.deletable = p.can_be_deleted()

    share_url = request.build_absolute_uri(
        reverse("split_external_auth", kwargs={"share_token": event.share_token})
    )
    return render(
        request,
        "splits/fragments/participants/manage.html",
        {
            "event": event,
            "participants": participants,
            "wygiwyh_form": wygiwyh_form or AddWygiwyhParticipantForm(event=event),
            "external_form": external_form or AddExternalParticipantForm(event=event),
            "share_url": share_url,
        },
    )


@only_htmx
@login_required
def participants_manage(request, event_id):
    actor = get_wygiwyh_actor(request, event_id)
    if not actor.is_creator:
        raise PermissionDenied
    return _render_participants_manage(request, actor)


@only_htmx
@login_required
@require_http_methods(["POST"])
def participant_add_wygiwyh(request, event_id):
    actor = get_wygiwyh_actor(request, event_id)
    if not actor.is_creator:
        raise PermissionDenied

    form = AddWygiwyhParticipantForm(request.POST, event=actor.event)
    if form.is_valid():
        u = form.cleaned_data["user"]
        base_name = user_display_name(u)
        name = base_name
        suffix = 2
        while actor.event.participants.filter(name__iexact=name).exists():
            name = f"{base_name} ({suffix})"
            suffix += 1
        SplitParticipant.objects.create(
            event=actor.event,
            user=u,
            name=name,
            is_external=False,
            is_active=True,
        )
        messages.success(request, _("Added %(name)s to the event") % {"name": name})
        resp = _render_participants_manage(request, actor)
        resp["HX-Trigger"] = "updated, toasts"
        return resp

    return _render_participants_manage(request, actor, wygiwyh_form=form)


@only_htmx
@login_required
@require_http_methods(["POST"])
def participant_add_external(request, event_id):
    actor = get_wygiwyh_actor(request, event_id)
    if not actor.is_creator:
        raise PermissionDenied

    form = AddExternalParticipantForm(request.POST, event=actor.event)
    if form.is_valid():
        name = form.cleaned_data["name"]
        SplitParticipant.objects.create(
            event=actor.event,
            user=None,
            name=name,
            is_external=True,
            is_active=True,
        )
        messages.success(
            request,
            _("Added external participant %(name)s") % {"name": name},
        )
        resp = _render_participants_manage(request, actor)
        resp["HX-Trigger"] = "updated, toasts"
        return resp

    return _render_participants_manage(request, actor, external_form=form)


@only_htmx
@login_required
@require_http_methods(["POST"])
def participant_toggle_active(request, event_id, participant_id):
    actor = get_wygiwyh_actor(request, event_id)
    if not actor.is_creator:
        raise PermissionDenied

    participant = get_object_or_404(
        SplitParticipant, id=participant_id, event=actor.event
    )
    if participant.is_creator:
        messages.error(request, _("The event creator cannot be deactivated."))
    else:
        participant.is_active = not participant.is_active
        participant.save(update_fields=["is_active"])
        if participant.is_active:
            messages.success(
                request, _("Reactivated %(name)s") % {"name": participant.name}
            )
        else:
            messages.success(
                request,
                _("Deactivated %(name)s (contributions preserved)")
                % {"name": participant.name},
            )

    resp = _render_participants_manage(request, actor)
    resp["HX-Trigger"] = "updated, toasts"
    return resp


@only_htmx
@login_required
@require_http_methods(["DELETE"])
def participant_delete(request, event_id, participant_id):
    actor = get_wygiwyh_actor(request, event_id)
    if not actor.is_creator:
        raise PermissionDenied

    participant = get_object_or_404(
        SplitParticipant, id=participant_id, event=actor.event
    )
    if participant.can_be_deleted():
        name = participant.name
        participant.delete()
        messages.success(request, _("Removed %(name)s") % {"name": name})
    else:
        messages.error(
            request,
            _(
                "%(name)s has existing contributions and cannot be deleted. Deactivate them instead."
            )
            % {"name": participant.name},
        )

    resp = _render_participants_manage(request, actor)
    resp["HX-Trigger"] = "updated, toasts"
    return resp


@only_htmx
@login_required
@require_http_methods(["POST"])
def participant_reset_password(request, event_id, participant_id):
    actor = get_wygiwyh_actor(request, event_id)
    if not actor.is_creator:
        raise PermissionDenied

    participant = get_object_or_404(
        SplitParticipant, id=participant_id, event=actor.event, is_external=True
    )
    participant.reset_external_password()
    messages.success(
        request,
        _("Password reset for %(name)s. They can set a new password on next login.")
        % {"name": participant.name},
    )
    resp = _render_participants_manage(request, actor)
    resp["HX-Trigger"] = "updated, toasts"
    return resp


@only_htmx
@login_required
@require_http_methods(["POST"])
def event_regenerate_link(request, event_id):
    actor = get_wygiwyh_actor(request, event_id)
    if not actor.is_creator:
        raise PermissionDenied

    actor.event.regenerate_share_token()
    messages.success(
        request,
        _("Share link regenerated. Existing external sessions have been signed out."),
    )
    resp = _render_participants_manage(request, actor)
    resp["HX-Trigger"] = "updated, toasts"
    return resp


# =============================================================================
# Shared Expense / Payment / Attachment Handlers (WYGIWYH + External)
# =============================================================================


def _handle_expense_add(request, actor: SplitActor):
    urls = _portal_urls(actor)
    if request.method == "POST":
        form = SplitExpenseForm(
            request.POST,
            request.FILES,
            event=actor.event,
            default_payer=actor.participant,
        )
        if form.is_valid():
            _save_expense_from_form(
                form,
                actor=actor,
                files=form.cleaned_data.get("attachments") or [],
            )
            messages.success(request, _("Expense added successfully"))
            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "updated, hide_offcanvas, toasts"},
            )
    else:
        form = SplitExpenseForm(event=actor.event, default_payer=actor.participant)

    ctx = _build_expense_form_context(form, actor, post_url=urls["expense_add"])
    return render(request, "splits/fragments/expense/form.html", ctx)


def _handle_expense_edit(request, actor: SplitActor, expense_id: int):
    expense = get_object_or_404(
        SplitExpense.objects.prefetch_related("shares__participant", "attachments"),
        id=expense_id,
        event=actor.event,
    )
    if not actor.can_edit_item(
        created_by_id=expense.created_by_participant_id,
        primary_participant_id=expense.paid_by_id,
    ):
        raise PermissionDenied

    urls = _portal_urls(actor)
    post_url = reverse(
        urls["expense_edit_name"],
        kwargs={urls["url_kwarg_key"]: urls["url_kwarg_val"], "expense_id": expense.id},
    )

    if request.method == "POST":
        form = SplitExpenseForm(
            request.POST,
            request.FILES,
            instance=expense,
            event=actor.event,
        )
        if form.is_valid():
            _save_expense_from_form(
                form,
                actor=actor,
                files=form.cleaned_data.get("attachments") or [],
            )
            messages.success(request, _("Expense updated successfully"))
            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "updated, hide_offcanvas, toasts"},
            )
    else:
        form = SplitExpenseForm(instance=expense, event=actor.event)

    ctx = _build_expense_form_context(form, actor, expense=expense, post_url=post_url)
    return render(request, "splits/fragments/expense/form.html", ctx)


def _handle_expense_delete(request, actor: SplitActor, expense_id: int):
    expense = get_object_or_404(SplitExpense, id=expense_id, event=actor.event)
    if not actor.can_edit_item(
        created_by_id=expense.created_by_participant_id,
        primary_participant_id=expense.paid_by_id,
    ):
        raise PermissionDenied

    for att in expense.attachments.all():
        att.file.delete(save=False)
    expense.delete()
    messages.success(request, _("Expense deleted successfully"))
    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "updated, hide_offcanvas, toasts"},
    )


def _handle_payment_add(request, actor: SplitActor):
    urls = _portal_urls(actor)
    initial = {}
    if request.method == "GET":
        if request.GET.get("from"):
            initial["from_participant"] = request.GET.get("from")
        elif actor.participant:
            initial["from_participant"] = actor.participant.id
        if request.GET.get("to"):
            initial["to_participant"] = request.GET.get("to")
        try:
            # Settle-up links send a plain "12.34", not the user's number format
            initial["amount"] = Decimal(request.GET["amount"])
        except (KeyError, InvalidOperation):
            pass

    if request.method == "POST":
        form = SplitPaymentForm(request.POST, request.FILES, event=actor.event, actor=actor)
        if form.is_valid():
            _save_payment_from_form(
                form,
                actor=actor,
                files=form.cleaned_data.get("attachments") or [],
            )
            messages.success(request, _("Payment recorded successfully"))
            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "updated, hide_offcanvas, toasts"},
            )
    else:
        form = SplitPaymentForm(event=actor.event, actor=actor, initial=initial)

    return render(
        request,
        "splits/fragments/payment/form.html",
        {
            "form": form,
            "event": actor.event,
            "actor": actor,
            "payment": None,
            "post_url": urls["payment_add"],
            "urls": urls,
        },
    )


def _handle_payment_edit(request, actor: SplitActor, payment_id: int):
    payment = get_object_or_404(
        SplitPayment.objects.prefetch_related("attachments"),
        id=payment_id,
        event=actor.event,
    )
    if not actor.can_edit_item(
        created_by_id=payment.created_by_participant_id,
        primary_participant_id=payment.from_participant_id,
    ):
        raise PermissionDenied

    urls = _portal_urls(actor)
    post_url = reverse(
        urls["payment_edit_name"],
        kwargs={urls["url_kwarg_key"]: urls["url_kwarg_val"], "payment_id": payment.id},
    )

    if request.method == "POST":
        form = SplitPaymentForm(
            request.POST, request.FILES, instance=payment, event=actor.event, actor=actor
        )
        if form.is_valid():
            _save_payment_from_form(
                form,
                actor=actor,
                files=form.cleaned_data.get("attachments") or [],
            )
            messages.success(request, _("Payment updated successfully"))
            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "updated, hide_offcanvas, toasts"},
            )
    else:
        form = SplitPaymentForm(instance=payment, event=actor.event, actor=actor)

    return render(
        request,
        "splits/fragments/payment/form.html",
        {
            "form": form,
            "event": actor.event,
            "actor": actor,
            "payment": payment,
            "post_url": post_url,
            "urls": urls,
        },
    )


def _handle_payment_delete(request, actor: SplitActor, payment_id: int):
    payment = get_object_or_404(SplitPayment, id=payment_id, event=actor.event)
    if not actor.can_edit_item(
        created_by_id=payment.created_by_participant_id,
        primary_participant_id=payment.from_participant_id,
    ):
        raise PermissionDenied

    for att in payment.attachments.all():
        att.file.delete(save=False)
    payment.delete()
    messages.success(request, _("Payment deleted successfully"))
    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "updated, hide_offcanvas, toasts"},
    )


INLINE_SAFE_CONTENT_TYPES = {
    "application/pdf",
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/webp",
}


def _handle_attachment_download(actor: SplitActor, attachment_id):
    att = get_object_or_404(SplitAttachment, id=attachment_id, event=actor.event)
    # Anonymous external participants upload these, so never render HTML/SVG inline
    return FileResponse(
        att.file.open("rb"),
        as_attachment=att.content_type not in INLINE_SAFE_CONTENT_TYPES,
        filename=att.original_name,
        content_type=att.content_type or "application/octet-stream",
    )


def _handle_attachment_delete(request, actor: SplitActor, attachment_id):
    att = get_object_or_404(SplitAttachment, id=attachment_id, event=actor.event)
    can_delete = actor.is_creator or (
        actor.participant and att.uploaded_by_id == actor.participant.id
    )
    if not can_delete and att.expense_id:
        can_delete = actor.can_edit_item(
            created_by_id=att.expense.created_by_participant_id,
            primary_participant_id=att.expense.paid_by_id,
        )
    if not can_delete and att.payment_id:
        can_delete = actor.can_edit_item(
            created_by_id=att.payment.created_by_participant_id,
            primary_participant_id=att.payment.from_participant_id,
        )
    if not can_delete:
        raise PermissionDenied

    att.file.delete(save=False)
    att.delete()
    messages.success(request, _("Attachment deleted"))
    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "updated, toasts"},
    )


# WYGIWYH wrappers
@only_htmx
@login_required
def expense_add(request, event_id):
    return _handle_expense_add(request, get_wygiwyh_actor(request, event_id))


@only_htmx
@login_required
def expense_edit(request, event_id, expense_id):
    return _handle_expense_edit(request, get_wygiwyh_actor(request, event_id), expense_id)


@only_htmx
@login_required
@require_http_methods(["DELETE"])
def expense_delete(request, event_id, expense_id):
    return _handle_expense_delete(request, get_wygiwyh_actor(request, event_id), expense_id)


@only_htmx
@login_required
def payment_add(request, event_id):
    return _handle_payment_add(request, get_wygiwyh_actor(request, event_id))


@only_htmx
@login_required
def payment_edit(request, event_id, payment_id):
    return _handle_payment_edit(request, get_wygiwyh_actor(request, event_id), payment_id)


@only_htmx
@login_required
@require_http_methods(["DELETE"])
def payment_delete(request, event_id, payment_id):
    return _handle_payment_delete(request, get_wygiwyh_actor(request, event_id), payment_id)


@login_required
@require_http_methods(["GET"])
def attachment_download(request, event_id, attachment_id):
    return _handle_attachment_download(get_wygiwyh_actor(request, event_id), attachment_id)


@only_htmx
@login_required
@require_http_methods(["DELETE"])
def attachment_delete(request, event_id, attachment_id):
    return _handle_attachment_delete(request, get_wygiwyh_actor(request, event_id), attachment_id)


# =============================================================================
# WYGIWYH Transaction Integration Views
# =============================================================================


def _handle_sync_view(
    request,
    *,
    actor: SplitActor,
    kind: str,
    default_amount: Decimal,
    default_date,
    default_notes: str,
    post_url: str,
    title: str,
    expense: SplitExpense | None = None,
    payment: SplitPayment | None = None,
    counterparty: SplitParticipant | None = None,
    default_is_paid: bool = True,
):
    tx_type = expected_transaction_type_for_kind(kind)
    default_desc = build_default_sync_description(
        event=actor.event,
        kind=kind,
        expense=expense,
        payment=payment,
        counterparty=counterparty,
    )

    if request.method == "POST":
        form = SplitTransactionSyncForm(
            request.POST,
            user=actor.user,
            event=actor.event,
            tx_type=tx_type,
        )
        if form.is_valid():
            if form.cleaned_data["mode"] == SplitTransactionSyncForm.Mode.CREATE:
                create_and_link_transaction(
                    user=actor.user,
                    event=actor.event,
                    kind=kind,
                    account=form.cleaned_data["account"],
                    amount=form.cleaned_data["amount"],
                    date=form.cleaned_data["date"],
                    description=form.cleaned_data["description"] or default_desc,
                    is_paid=form.cleaned_data["is_paid"],
                    category=form.cleaned_data.get("category"),
                    tags=form.cleaned_data.get("tags") or [],
                    entities=form.cleaned_data.get("entities") or [],
                    notes=form.cleaned_data.get("notes", ""),
                    expense=expense,
                    payment=payment,
                    counterparty=counterparty,
                )
                messages.success(
                    request, _("Transaction created and linked")
                )
            else:
                link_existing_transaction(
                    user=actor.user,
                    event=actor.event,
                    kind=kind,
                    tx=form.cleaned_data["existing_transaction"],
                    expense=expense,
                    payment=payment,
                    counterparty=counterparty,
                )
                messages.success(
                    request, _("Transaction linked")
                )
            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "updated, hide_offcanvas, toasts"},
            )
    else:
        form = SplitTransactionSyncForm(
            user=actor.user,
            event=actor.event,
            tx_type=tx_type,
            initial={
                "mode": SplitTransactionSyncForm.Mode.CREATE,
                "amount": default_amount,
                "date": default_date,
                "description": default_desc,
                "is_paid": default_is_paid,
                "notes": default_notes,
            },
        )

    return render(
        request,
        "splits/fragments/sync/form.html",
        {
            "form": form,
            "event": actor.event,
            "post_url": post_url,
            "title": title,
            "tx_type": tx_type,
        },
    )


@only_htmx
@login_required
def sync_expense(request, event_id, expense_id):
    actor = get_wygiwyh_actor(request, event_id)
    # Only the payer's money left one of their accounts
    expense = get_object_or_404(
        SplitExpense,
        id=expense_id,
        event=actor.event,
        paid_by=actor.participant,
    )
    return _handle_sync_view(
        request,
        actor=actor,
        kind=SplitTransactionLink.Kind.EXPENSE,
        default_amount=expense.amount,
        default_date=expense.date,
        default_notes=expense.notes,
        post_url=reverse(
            "split_sync_expense",
            kwargs={"event_id": actor.event.id, "expense_id": expense.id},
        ),
        title=_("Add expense to my transactions"),
        expense=expense,
        default_is_paid=True,
    )


@only_htmx
@login_required
def sync_payment(request, event_id, payment_id):
    actor = get_wygiwyh_actor(request, event_id)
    payment = get_object_or_404(
        SplitPayment.objects.select_related("from_participant", "to_participant"),
        id=payment_id,
        event=actor.event,
    )
    me = actor.participant.id if actor.participant else None
    if payment.to_participant_id == me:
        kind = SplitTransactionLink.Kind.PAYMENT_IN
        counterparty = payment.from_participant
        title = _("Add received payment to my transactions")
    elif payment.from_participant_id == me:
        kind = SplitTransactionLink.Kind.PAYMENT_OUT
        counterparty = payment.to_participant
        title = _("Add sent payment to my transactions")
    else:
        raise Http404

    return _handle_sync_view(
        request,
        actor=actor,
        kind=kind,
        default_amount=payment.amount,
        default_date=payment.date,
        default_notes=payment.notes,
        post_url=reverse(
            "split_sync_payment",
            kwargs={"event_id": actor.event.id, "payment_id": payment.id},
        ),
        title=title,
        payment=payment,
        counterparty=counterparty,
        default_is_paid=True,
    )


@only_htmx
@login_required
def sync_settlement(request, event_id):
    actor = get_wygiwyh_actor(request, event_id)
    direction = request.GET.get("direction") or request.POST.get("direction") or "out"
    counterparty_id = request.GET.get("counterparty") or request.POST.get("counterparty")
    raw_amount = request.GET.get("amount") or request.POST.get("amount") or "0"

    counterparty = get_object_or_404(
        SplitParticipant, id=counterparty_id, event=actor.event
    )
    try:
        amount = Decimal(str(raw_amount))
    except InvalidOperation:
        amount = Decimal("0")

    if direction == "in":
        kind = SplitTransactionLink.Kind.SETTLEMENT_IN
        title = _("Expected payment from %(name)s") % {
            "name": counterparty.name
        }
    else:
        kind = SplitTransactionLink.Kind.SETTLEMENT_OUT
        title = _("Planned payment to %(name)s") % {
            "name": counterparty.name
        }

    post_url = (
        reverse("split_sync_settlement", kwargs={"event_id": actor.event.id})
        + f"?direction={direction}&counterparty={counterparty.id}&amount={amount}"
    )
    return _handle_sync_view(
        request,
        actor=actor,
        kind=kind,
        default_amount=amount,
        default_date=timezone.localdate(),
        default_notes="",
        post_url=post_url,
        title=title,
        counterparty=counterparty,
        default_is_paid=False,
    )


@only_htmx
@login_required
@require_http_methods(["DELETE"])
def sync_unlink(request, event_id, link_id):
    actor = get_wygiwyh_actor(request, event_id)
    link = get_object_or_404(
        SplitTransactionLink,
        id=link_id,
        event=actor.event,
        user=actor.user,
    )
    link.delete()
    messages.success(request, _("Transaction unlinked"))
    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "updated, toasts"},
    )


# =============================================================================
# External Participant Portal Views (No WYGIWYH Account Required!)
# =============================================================================


def external_auth(request, share_token):
    event = get_object_or_404(
        SplitEvent.objects.select_related("currency", "creator"),
        share_token=share_token,
    )
    if not event.allow_external_access:
        return render(
            request,
            "splits/pages/external_disabled.html",
            {"event": event},
            status=403,
        )

    existing = get_external_participant_from_session(request, event)
    if existing:
        return redirect("split_external_event_detail", share_token=event.share_token)

    external_participants = list(
        event.participants.filter(is_external=True, is_active=True).order_by(
            "name", "id"
        )
    )

    if request.method == "POST":
        form = ExternalAuthForm(request.POST, event=event)
        if form.is_valid():
            participant: SplitParticipant = form.cleaned_data["participant"]
            if not participant.is_claimed:
                participant.set_external_password(
                    form.cleaned_data["password"],
                    username=form.cleaned_data.get("username", ""),
                )
            set_external_session(request, event, participant)
            return redirect(
                "split_external_event_detail", share_token=event.share_token
            )
    else:
        form = ExternalAuthForm(event=event)

    return render(
        request,
        "splits/pages/external_auth.html",
        {
            "event": event,
            "form": form,
            "external_participants": external_participants,
            "claimed_ids": [p.id for p in external_participants if p.is_claimed],
        },
    )


@require_http_methods(["POST"])
def external_logout(request, share_token):
    event = get_object_or_404(SplitEvent, share_token=share_token)
    clear_external_session(request, event)
    return redirect("split_external_auth", share_token=event.share_token)


def external_event_detail(request, share_token):
    actor = get_external_actor(request, share_token)
    if actor is None:
        return redirect("split_external_auth", share_token=share_token)
    return render(
        request,
        "splits/pages/external_event_detail.html",
        {
            "event": actor.event,
            "actor": actor,
            "urls": _portal_urls(actor),
        },
    )


@only_htmx
def external_event_content(request, share_token):
    actor = get_external_actor(request, share_token)
    if actor is None:
        return HttpResponse(
            status=401,
            headers={
                "HX-Redirect": reverse(
                    "split_external_auth", kwargs={"share_token": share_token}
                )
            },
        )
    ctx = _build_event_context(request, actor)
    return render(request, "splits/fragments/event/content.html", ctx)


def external_event_report(request, share_token):
    actor = get_external_actor(request, share_token)
    if actor is None:
        return redirect("split_external_auth", share_token=share_token)
    return render(
        request, "splits/pages/event_report.html", _build_event_context(request, actor)
    )


@only_htmx
@require_http_methods(["GET"])
def external_toasts(request, share_token):
    actor = get_external_actor(request, share_token)
    if actor is None:
        return HttpResponse(status=204)
    return render(request, "common/fragments/toasts.html")


@only_htmx
def external_expense_add(request, share_token):
    actor = get_external_actor(request, share_token)
    if actor is None:
        return HttpResponse(status=401)
    return _handle_expense_add(request, actor)


@only_htmx
def external_expense_edit(request, share_token, expense_id):
    actor = get_external_actor(request, share_token)
    if actor is None:
        return HttpResponse(status=401)
    return _handle_expense_edit(request, actor, expense_id)


@only_htmx
@require_http_methods(["DELETE"])
def external_expense_delete(request, share_token, expense_id):
    actor = get_external_actor(request, share_token)
    if actor is None:
        return HttpResponse(status=401)
    return _handle_expense_delete(request, actor, expense_id)


@only_htmx
def external_payment_add(request, share_token):
    actor = get_external_actor(request, share_token)
    if actor is None:
        return HttpResponse(status=401)
    return _handle_payment_add(request, actor)


@only_htmx
def external_payment_edit(request, share_token, payment_id):
    actor = get_external_actor(request, share_token)
    if actor is None:
        return HttpResponse(status=401)
    return _handle_payment_edit(request, actor, payment_id)


@only_htmx
@require_http_methods(["DELETE"])
def external_payment_delete(request, share_token, payment_id):
    actor = get_external_actor(request, share_token)
    if actor is None:
        return HttpResponse(status=401)
    return _handle_payment_delete(request, actor, payment_id)


@require_http_methods(["GET"])
def external_attachment_download(request, share_token, attachment_id):
    actor = get_external_actor(request, share_token)
    if actor is None:
        return redirect("split_external_auth", share_token=share_token)
    return _handle_attachment_download(actor, attachment_id)


@only_htmx
@require_http_methods(["DELETE"])
def external_attachment_delete(request, share_token, attachment_id):
    actor = get_external_actor(request, share_token)
    if actor is None:
        return HttpResponse(status=401)
    return _handle_attachment_delete(request, actor, attachment_id)
