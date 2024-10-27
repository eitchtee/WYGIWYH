from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.common.decorators.htmx import only_htmx
from apps.rules.forms import TransactionRuleForm, TransactionRuleActionForm
from apps.rules.models import TransactionRule, TransactionRuleAction


@login_required
@require_http_methods(["GET"])
def rules_index(request):
    return render(
        request,
        "rules/pages/index.html",
    )


@only_htmx
@login_required
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
            "HX-Trigger": "updated, hide_offcanvas, toasts",
        },
    )


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def transaction_rule_add(request, **kwargs):
    if request.method == "POST":
        form = TransactionRuleForm(request.POST)
        if form.is_valid():
            instance = form.save()
            messages.success(request, _("Rule added successfully"))

            return redirect("transaction_rule_action_add", instance.id)
    else:
        form = TransactionRuleForm()

    return render(
        request,
        "rules/fragments/transaction_rule/add.html",
        {"form": form},
    )


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def transaction_rule_edit(request, transaction_rule_id):
    transaction_rule = get_object_or_404(TransactionRule, id=transaction_rule_id)

    if request.method == "POST":
        form = TransactionRuleForm(request.POST, instance=transaction_rule)
        if form.is_valid():
            form.save()
            messages.success(request, _("Rule updated successfully"))

            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": "updated, hide_offcanvas, toasts",
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
@require_http_methods(["GET", "POST"])
def transaction_rule_view(request, transaction_rule_id):
    transaction_rule = get_object_or_404(TransactionRule, id=transaction_rule_id)

    return render(
        request,
        "rules/fragments/transaction_rule/view.html",
        {"transaction_rule": transaction_rule},
    )


@only_htmx
@login_required
@csrf_exempt
@require_http_methods(["DELETE"])
def transaction_rule_delete(request, transaction_rule_id):
    transaction_rule = get_object_or_404(TransactionRule, id=transaction_rule_id)

    transaction_rule.delete()

    messages.success(request, _("Rule deleted successfully"))

    return HttpResponse(
        status=204,
        headers={
            "HX-Trigger": "updated, hide_offcanvas, toasts",
        },
    )


@only_htmx
@login_required
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
                    "HX-Trigger": "updated, hide_offcanvas, toasts",
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
                    "HX-Trigger": "updated, hide_offcanvas, toasts",
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
@csrf_exempt
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
            "HX-Trigger": "updated, hide_offcanvas, toasts",
        },
    )
