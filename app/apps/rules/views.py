from itertools import chain

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from apps.common.decorators.htmx import only_htmx
from apps.rules.forms import (
    TransactionRuleForm,
    TransactionRuleActionForm,
    UpdateOrCreateTransactionRuleActionForm,
)
from apps.rules.models import (
    TransactionRule,
    TransactionRuleAction,
    UpdateOrCreateTransactionRuleAction,
)
from apps.common.models import SharedObject
from apps.common.forms import SharedObjectForm
from apps.common.decorators.demo import disabled_on_demo


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
    transaction_rules = TransactionRule.objects.all().order_by("id")
    return render(
        request,
        "rules/fragments/list.html",
        {"transaction_rules": transaction_rules},
    )


@only_htmx
@login_required
@disabled_on_demo
@require_http_methods(["GET", "POST"])
def transaction_rule_toggle_activity(request, transaction_rule_id, **kwargs):
    transaction_rule = get_object_or_404(TransactionRule, id=transaction_rule_id)
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
    transaction_rule = get_object_or_404(TransactionRule, id=transaction_rule_id)

    if transaction_rule.owner and transaction_rule.owner != request.user:
        messages.error(request, _("Only the owner can edit this"))

        return HttpResponse(
            status=204,
            headers={
                "HX-Trigger": "updated, hide_offcanvas",
            },
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
    transaction_rule = get_object_or_404(TransactionRule, id=transaction_rule_id)

    edit_actions = transaction_rule.transaction_actions.all()
    update_or_create_actions = transaction_rule.update_or_create_transaction_actions.all()

    all_actions = sorted(
        chain(edit_actions, update_or_create_actions),
        key=lambda a: a.order,
    )

    return render(
        request,
        "rules/fragments/transaction_rule/view.html",
        {"transaction_rule": transaction_rule, "all_actions": all_actions},
    )


@only_htmx
@login_required
@disabled_on_demo
@require_http_methods(["DELETE"])
def transaction_rule_delete(request, transaction_rule_id):
    transaction_rule = get_object_or_404(TransactionRule, id=transaction_rule_id)

    if (
        transaction_rule.owner != request.user
        and request.user in transaction_rule.shared_with.all()
    ):
        transaction_rule.shared_with.remove(request.user)
        messages.success(request, _("Item no longer shared with you"))
    else:
        transaction_rule.delete()
        messages.success(request, _("Rule deleted successfully"))

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
    transaction_rule = get_object_or_404(TransactionRule, id=transaction_rule_id)

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
    obj = get_object_or_404(TransactionRule, id=pk)

    if obj.owner and obj.owner != request.user:
        messages.error(request, _("Only the owner can edit this"))

        return HttpResponse(
            status=204,
            headers={
                "HX-Trigger": "updated, hide_offcanvas",
            },
        )

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
    transaction_rule = get_object_or_404(TransactionRule, id=transaction_rule_id)

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
    transaction_rule_action = get_object_or_404(
        TransactionRuleAction, id=transaction_rule_action_id
    )
    transaction_rule = get_object_or_404(
        TransactionRule, id=transaction_rule_action.rule.id
    )

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
    transaction_rule_action = get_object_or_404(
        TransactionRuleAction, id=transaction_rule_action_id
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
    transaction_rule = get_object_or_404(TransactionRule, id=transaction_rule_id)

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
    linked_action = get_object_or_404(UpdateOrCreateTransactionRuleAction, id=pk)
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
    linked_action = get_object_or_404(UpdateOrCreateTransactionRuleAction, id=pk)

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
