from itertools import chain

from copy import deepcopy

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods
from procrastinate.exceptions import AlreadyEnqueued

from apps.common.decorators.htmx import only_htmx
from apps.common.functions.permissions import (
    EDIT,
    READ,
    get_shared_object_or_error,
)
from apps.rules.forms import (
    TransactionRuleForm,
    TransactionRuleActionForm,
    UpdateOrCreateTransactionRuleActionForm,
    DryRunCreatedTransacion,
    DryRunDeletedTransacion,
    DryRunUpdatedTransactionForm,
    RunRulesForm,
)
from apps.rules.models import (
    RuleRun,
    TransactionRule,
    TransactionRuleAction,
    UpdateOrCreateTransactionRuleAction,
)
from apps.common.models import SharedObject
from apps.common.forms import SharedObjectForm
from apps.common.decorators.demo import disabled_on_demo
from apps.rules.tasks import (
    check_for_transaction_rules,
    run_rules_on_all_transactions,
)
from apps.common.middleware.thread_local import get_current_user
from apps.rules.signals import transaction_created, transaction_updated
from apps.rules.utils.transactions import serialize_transaction
from apps.transactions.models import Transaction


@login_required
@disabled_on_demo
@require_http_methods(["GET"])
def rules_index(request):
    return render(
        request,
        "rules/pages/index.html",
    )


@only_htmx
@login_required
@disabled_on_demo
@require_http_methods(["GET"])
def rules_list(request):
    transaction_rules = TransactionRule.objects.all().order_by("order", "id")
    return render(
        request,
        "rules/fragments/list.html",
        {
            "transaction_rules": transaction_rules,
            "runnable_rule_ids": set(
                TransactionRule.runnable_by(request.user).values_list("id", flat=True)
            ),
        },
    )


@only_htmx
@login_required
@disabled_on_demo
@require_http_methods(["GET", "POST"])
def rules_run(request):
    """Run the chosen rules against all existing transactions, in the background."""
    if request.method == "POST":
        form = RunRulesForm(request.POST, user=request.user)
        if form.is_valid():
            lock = f"run_rules_on_all_transactions_{request.user.id}"
            try:
                # Together, so a rejected job doesn't leave a run behind
                with transaction.atomic():
                    run = RuleRun.objects.create(
                        owner=request.user,
                        rules=[
                            {
                                "id": rule.id,
                                "name": rule.name,
                                "applied": 0,
                                "failed": 0,
                            }
                            for rule in form.cleaned_data["rules"]
                        ],
                    )
                    # One run per user at a time, with at most one more waiting
                    run_rules_on_all_transactions.configure(
                        lock=lock, queueing_lock=lock
                    ).defer(run_id=run.id)
            except AlreadyEnqueued:
                messages.error(
                    request,
                    _("A run is already waiting to start, try again later"),
                )
                return HttpResponse(
                    status=204,
                    headers={"HX-Trigger": "updated, hide_offcanvas"},
                )

            return render(request, "rules/fragments/runs/detail.html", {"run": run})
    else:
        rule_id = request.GET.get("rule", "")
        if rule_id.isdigit():
            initial = [int(rule_id)]
        else:
            # Delete-only rules are left unchecked: their transactions weren't deleted
            initial = TransactionRule.runnable_by(request.user).filter(
                Q(on_create=True) | Q(on_update=True), active=True
            )
        form = RunRulesForm(initial={"rules": initial}, user=request.user)

    return render(
        request,
        "rules/fragments/run.html",
        {"form": form, "transaction_count": Transaction.objects.count()},
    )


@only_htmx
@login_required
@disabled_on_demo
@require_http_methods(["GET"])
def rule_runs_list(request):
    runs = RuleRun.objects.filter(owner=request.user)[:20]
    return render(request, "rules/fragments/runs/list.html", {"runs": runs})


@only_htmx
@login_required
@disabled_on_demo
@require_http_methods(["GET"])
def rule_run_detail(request, pk):
    run = get_object_or_404(RuleRun, id=pk, owner=request.user)
    return render(request, "rules/fragments/runs/detail.html", {"run": run})


@only_htmx
@login_required
@disabled_on_demo
@require_http_methods(["GET"])
def rule_run_progress(request, pk):
    run = get_object_or_404(RuleRun, id=pk, owner=request.user)
    return render(
        request,
        "rules/fragments/runs/progress.html",
        {"run": run},
        # 286 tells htmx to stop polling
        status=286 if run.is_done else 200,
    )


@only_htmx
@login_required
@disabled_on_demo
@require_http_methods(["GET", "POST"])
def transaction_rule_toggle_activity(request, transaction_rule_id, **kwargs):
    transaction_rule = get_shared_object_or_error(
        TransactionRule, request, id=transaction_rule_id, level=EDIT
    )
    current_active = transaction_rule.active
    transaction_rule.active = not current_active
    transaction_rule.save(update_fields=["active"])

    if current_active:
        messages.success(request, _("Rule deactivated successfully"))
    else:
        messages.success(request, _("Rule activated successfully"))

    return HttpResponse(
        status=204,
        headers={
            "HX-Trigger": "updated, hide_offcanvas",
        },
    )


@only_htmx
@login_required
@disabled_on_demo
@require_http_methods(["GET", "POST"])
def transaction_rule_add(request, **kwargs):
    if request.method == "POST":
        form = TransactionRuleForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("Rule added successfully"))

            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": "updated, hide_offcanvas",
                },
            )
    else:
        form = TransactionRuleForm()

    return render(
        request,
        "rules/fragments/transaction_rule/add.html",
        {"form": form},
    )


@only_htmx
@login_required
@disabled_on_demo
@require_http_methods(["GET", "POST"])
def transaction_rule_edit(request, transaction_rule_id):
    transaction_rule = get_shared_object_or_error(
        TransactionRule, request, id=transaction_rule_id, level=EDIT
    )

    if request.method == "POST":
        form = TransactionRuleForm(request.POST, instance=transaction_rule)
        if form.is_valid():
            form.save()
            messages.success(request, _("Rule updated successfully"))

            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": "updated, hide_offcanvas",
                },
            )
    else:
        form = TransactionRuleForm(instance=transaction_rule)

    return render(
        request,
        "rules/fragments/transaction_rule/edit.html",
        {"form": form, "transaction_rule": transaction_rule},
    )


@only_htmx
@login_required
@disabled_on_demo
@require_http_methods(["GET", "POST"])
def transaction_rule_view(request, transaction_rule_id):
    transaction_rule = get_shared_object_or_error(
        TransactionRule, request, id=transaction_rule_id, level=READ
    )

    edit_actions = transaction_rule.transaction_actions.all()
    update_or_create_actions = (
        transaction_rule.update_or_create_transaction_actions.all()
    )

    all_actions = sorted(
        chain(edit_actions, update_or_create_actions),
        key=lambda a: a.order,
    )

    return render(
        request,
        "rules/fragments/transaction_rule/view.html",
        {
            "transaction_rule": transaction_rule,
            "all_actions": all_actions,
            "can_run": TransactionRule.runnable_by(request.user)
            .filter(id=transaction_rule.id)
            .exists(),
        },
    )


@only_htmx
@login_required
@disabled_on_demo
@require_http_methods(["DELETE"])
def transaction_rule_delete(request, transaction_rule_id):
    transaction_rule = get_shared_object_or_error(
        TransactionRule, request, id=transaction_rule_id, level=READ
    )

    if transaction_rule.is_editable_by(request.user):
        transaction_rule.delete()
        messages.success(request, _("Rule deleted successfully"))
    elif transaction_rule.shared_with.filter(pk=request.user.pk).exists():
        # Someone else's rule shared with us: we can drop our own access to it,
        # but never delete it.
        transaction_rule.shared_with.remove(request.user)
        messages.success(request, _("Item no longer shared with you"))
    else:
        raise PermissionDenied

    return HttpResponse(
        status=204,
        headers={
            "HX-Trigger": "updated, hide_offcanvas",
        },
    )


@only_htmx
@login_required
@disabled_on_demo
@require_http_methods(["GET"])
def transaction_rule_take_ownership(request, transaction_rule_id):
    transaction_rule = get_shared_object_or_error(
        TransactionRule, request, id=transaction_rule_id, level=EDIT
    )

    if not transaction_rule.owner:
        transaction_rule.owner = request.user
        transaction_rule.visibility = SharedObject.Visibility.private
        transaction_rule.save()

        messages.success(request, _("Ownership taken successfully"))

    return HttpResponse(
        status=204,
        headers={
            "HX-Trigger": "updated, hide_offcanvas",
        },
    )


@only_htmx
@login_required
@disabled_on_demo
@require_http_methods(["GET", "POST"])
def transaction_rule_share(request, pk):
    obj = get_shared_object_or_error(TransactionRule, request, id=pk, level=EDIT)

    if request.method == "POST":
        form = SharedObjectForm(request.POST, instance=obj, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, _("Configuration saved successfully"))

            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": "updated, hide_offcanvas",
                },
            )
    else:
        form = SharedObjectForm(instance=obj, user=request.user)

    return render(
        request,
        "rules/fragments/share.html",
        {"form": form, "object": obj},
    )


@only_htmx
@login_required
@disabled_on_demo
@require_http_methods(["GET", "POST"])
def transaction_rule_action_add(request, transaction_rule_id):
    transaction_rule = get_shared_object_or_error(
        TransactionRule, request, id=transaction_rule_id, level=EDIT
    )

    if request.method == "POST":
        form = TransactionRuleActionForm(request.POST, rule=transaction_rule)
        if form.is_valid():
            form.save()

            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": "updated, hide_offcanvas",
                },
            )
    else:
        form = TransactionRuleActionForm(rule=transaction_rule)

    return render(
        request,
        "rules/fragments/transaction_rule/transaction_rule_action/add.html",
        {"form": form, "transaction_rule_id": transaction_rule_id},
    )


@only_htmx
@login_required
@disabled_on_demo
@require_http_methods(["GET", "POST"])
def transaction_rule_action_edit(request, transaction_rule_action_id):
    transaction_rule_action = get_shared_object_or_error(
        TransactionRuleAction,
        request,
        id=transaction_rule_action_id,
        level=EDIT,
        via="rule",
    )
    transaction_rule = transaction_rule_action.rule

    if request.method == "POST":
        form = TransactionRuleActionForm(
            request.POST, instance=transaction_rule_action, rule=transaction_rule
        )
        if form.is_valid():
            form.save()
            messages.success(request, _("Action updated successfully"))

            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": "updated, hide_offcanvas",
                },
            )
    else:
        form = TransactionRuleActionForm(
            instance=transaction_rule_action, rule=transaction_rule
        )

    return render(
        request,
        "rules/fragments/transaction_rule/transaction_rule_action/edit.html",
        {"form": form, "transaction_rule_action": transaction_rule_action},
    )


@only_htmx
@login_required
@disabled_on_demo
@require_http_methods(["DELETE"])
def transaction_rule_action_delete(request, transaction_rule_action_id):
    transaction_rule_action = get_shared_object_or_error(
        TransactionRuleAction,
        request,
        id=transaction_rule_action_id,
        level=EDIT,
        via="rule",
    )

    transaction_rule_action.delete()

    messages.success(request, _("Action deleted successfully"))

    return HttpResponse(
        status=204,
        headers={
            "HX-Trigger": "updated, hide_offcanvas",
        },
    )


@only_htmx
@login_required
@disabled_on_demo
@require_http_methods(["GET", "POST"])
def update_or_create_transaction_rule_action_add(request, transaction_rule_id):
    transaction_rule = get_shared_object_or_error(
        TransactionRule, request, id=transaction_rule_id, level=EDIT
    )

    if request.method == "POST":
        form = UpdateOrCreateTransactionRuleActionForm(
            request.POST, rule=transaction_rule
        )
        if form.is_valid():
            form.save()
            messages.success(
                request, _("Update or Create Transaction action added successfully")
            )
            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": "updated, hide_offcanvas",
                },
            )
    else:
        form = UpdateOrCreateTransactionRuleActionForm(rule=transaction_rule)

    return render(
        request,
        "rules/fragments/transaction_rule/update_or_create_transaction_rule_action/add.html",
        {"form": form, "transaction_rule_id": transaction_rule_id},
    )


@only_htmx
@login_required
@disabled_on_demo
@require_http_methods(["GET", "POST"])
def update_or_create_transaction_rule_action_edit(request, pk):
    linked_action = get_shared_object_or_error(
        UpdateOrCreateTransactionRuleAction, request, id=pk, level=EDIT, via="rule"
    )
    transaction_rule = linked_action.rule

    if request.method == "POST":
        form = UpdateOrCreateTransactionRuleActionForm(
            request.POST, instance=linked_action, rule=transaction_rule
        )
        if form.is_valid():
            form.save()
            messages.success(
                request, _("Update or Create Transaction action updated successfully")
            )
            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": "updated, hide_offcanvas",
                },
            )
    else:
        form = UpdateOrCreateTransactionRuleActionForm(
            instance=linked_action, rule=transaction_rule
        )

    return render(
        request,
        "rules/fragments/transaction_rule/update_or_create_transaction_rule_action/edit.html",
        {"form": form, "action": linked_action},
    )


@only_htmx
@login_required
@disabled_on_demo
@require_http_methods(["DELETE"])
def update_or_create_transaction_rule_action_delete(request, pk):
    linked_action = get_shared_object_or_error(
        UpdateOrCreateTransactionRuleAction, request, id=pk, level=EDIT, via="rule"
    )

    linked_action.delete()

    messages.success(
        request, _("Update or Create Transaction action deleted successfully")
    )

    return HttpResponse(
        status=204,
        headers={
            "HX-Trigger": "updated, hide_offcanvas",
        },
    )


@only_htmx
@login_required
@disabled_on_demo
@require_http_methods(["GET", "POST"])
def dry_run_rule_created(request, pk):
    rule = get_shared_object_or_error(TransactionRule, request, id=pk, level=EDIT)
    logs = None
    results = None

    if request.method == "POST":
        form = DryRunCreatedTransacion(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    logs, results = check_for_transaction_rules(
                        instance_id=form.cleaned_data["transaction"].id,
                        signal="transaction_created",
                        dry_run=True,
                        rule_id=rule.id,
                        user_id=get_current_user().id,
                    )
                    logs = "\n".join(logs)

                    response = render(
                        request,
                        "rules/fragments/transaction_rule/dry_run/created.html",
                        {"form": form, "rule": rule, "logs": logs, "results": results},
                    )

                    raise Exception("ROLLBACK")
            except Exception:
                pass

            return response

    else:
        form = DryRunCreatedTransacion()

    return render(
        request,
        "rules/fragments/transaction_rule/dry_run/created.html",
        {"form": form, "rule": rule, "logs": logs, "results": results},
    )


@only_htmx
@login_required
@disabled_on_demo
@require_http_methods(["GET", "POST"])
def dry_run_rule_deleted(request, pk):
    rule = get_shared_object_or_error(TransactionRule, request, id=pk, level=EDIT)
    logs = None
    results = None

    if request.method == "POST":
        form = DryRunDeletedTransacion(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    logs, results = check_for_transaction_rules(
                        instance_id=form.cleaned_data["transaction"].id,
                        signal="transaction_deleted",
                        dry_run=True,
                        rule_id=rule.id,
                        user_id=get_current_user().id,
                    )
                    logs = "\n".join(logs)

                    response = render(
                        request,
                        "rules/fragments/transaction_rule/dry_run/created.html",
                        {"form": form, "rule": rule, "logs": logs, "results": results},
                    )

                    raise Exception("ROLLBACK")
            except Exception:
                pass

        return response

    else:
        form = DryRunDeletedTransacion()

    return render(
        request,
        "rules/fragments/transaction_rule/dry_run/deleted.html",
        {"form": form, "rule": rule, "logs": logs, "results": results},
    )


@only_htmx
@login_required
@disabled_on_demo
@require_http_methods(["GET", "POST"])
def dry_run_rule_updated(request, pk):
    rule = get_shared_object_or_error(TransactionRule, request, id=pk, level=EDIT)
    logs = None
    results = None

    if request.method == "POST":
        form = DryRunUpdatedTransactionForm(request.POST)
        if form.is_valid():
            base_transaction = Transaction.objects.get(
                id=request.POST.get("transaction")
            )
            old_data = deepcopy(base_transaction)
            try:
                with transaction.atomic():
                    for field_name, value in form.cleaned_data.items():
                        if value or isinstance(
                            value, bool
                        ):  # Only update fields that have been filled in the form
                            if field_name == "tags":
                                base_transaction.tags.set(value)
                            elif field_name == "entities":
                                base_transaction.entities.set(value)
                            else:
                                setattr(base_transaction, field_name, value)

                    base_transaction.save()

                    logs, results = check_for_transaction_rules(
                        instance_id=base_transaction.id,
                        signal="transaction_updated",
                        dry_run=True,
                        rule_id=rule.id,
                        user_id=get_current_user().id,
                        old_data=old_data,
                    )
                    logs = "\n".join(logs) if logs else ""

                    response = render(
                        request,
                        "rules/fragments/transaction_rule/dry_run/updated.html",
                        {"form": form, "rule": rule, "logs": logs, "results": results},
                    )

                    # This will rollback the transaction
                    raise Exception("ROLLBACK")
            except Exception:
                pass

            return response
    else:
        form = DryRunUpdatedTransactionForm(initial={"is_paid": None, "type": None})

    return render(
        request,
        "rules/fragments/transaction_rule/dry_run/updated.html",
        {"form": form, "rule": rule, "logs": logs, "results": results},
    )
