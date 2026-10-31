from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import models
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _

from apps.accounts.forms import AccountBalanceFormSet, ReconciliationCutoffForm
from apps.accounts.models import Account, Transaction
from apps.accounts.services import get_account_balance
from apps.common.decorators.htmx import only_htmx


@only_htmx
@login_required
def account_reconciliation(request):
    cutoff = ReconciliationCutoffForm(
        request.POST if request.method == "POST" else request.GET or None
    )
    balance_filters = cutoff.balance_filters()

    initial_data = [
        {
            "account_id": account.id,
            "account_group": account.group,
            "account_name": account.name,
            "decimal_places": account.currency.decimal_places,
            "suffix": account.currency.suffix,
            "prefix": account.currency.prefix,
            "current_balance": get_account_balance(account, **balance_filters),
        }
        for account in Account.objects.filter(is_archived=False)
        .select_related("currency", "group")
        .order_by("group", "name")
    ]

    if request.method == "POST":
        formset = AccountBalanceFormSet(request.POST, initial=initial_data)
        if formset.is_valid() and cutoff.is_valid():
            adjustment_date, adjustment_reference_date = cutoff.adjustment_dates()
            with transaction.atomic():
                for form in formset:
                    if form.is_valid():
                        account_id = form.cleaned_data["account_id"]
                        new_balance = form.cleaned_data["new_balance"]
                        account = Account.objects.get(id=account_id)
                        category = form.cleaned_data["category"]
                        tags = form.cleaned_data.get("tags", [])

                        if new_balance is None:
                            continue

                        current_balance = get_account_balance(
                            account, **balance_filters
                        )
                        difference = new_balance - current_balance

                        if difference != 0:
                            new_transaction = Transaction.objects.create(
                                account=account,
                                type=(
                                    Transaction.Type.INCOME
                                    if difference > 0
                                    else Transaction.Type.EXPENSE
                                ),
                                amount=abs(difference),
                                date=adjustment_date,
                                reference_date=adjustment_reference_date,
                                description=_("Balance reconciliation"),
                                is_paid=True,
                                category=category,
                            )

                            new_transaction.tags.set(tags)

            messages.success(
                request, _("Account balances have been reconciled successfully")
            )
            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "updated, hide_offcanvas"},
            )
    else:
        formset = AccountBalanceFormSet(initial=initial_data)

    return render(
        request,
        "accounts/fragments/account_reconciliation.html",
        {"form": formset, "cutoff": cutoff},
    )
