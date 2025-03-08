from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import models
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.forms import AccountBalanceFormSet
from apps.accounts.models import Account, Transaction
from apps.common.decorators.htmx import only_htmx


@only_htmx
@login_required
def account_reconciliation(request):
    def get_account_balance(account):
        income = Transaction.objects.filter(
            account=account, type=Transaction.Type.INCOME, is_paid=True
        ).aggregate(total=models.Sum("amount"))["total"] or Decimal("0")

        expense = Transaction.objects.filter(
            account=account, type=Transaction.Type.EXPENSE, is_paid=True
        ).aggregate(total=models.Sum("amount"))["total"] or Decimal("0")

        return income - expense

    initial_data = [
        {
            "account_id": account.id,
            "account_group": account.group,
            "account_name": account.name,
            "decimal_places": account.currency.decimal_places,
            "suffix": account.currency.suffix,
            "prefix": account.currency.prefix,
            "current_balance": get_account_balance(account),
        }
        for account in Account.objects.filter(is_archived=False)
        .select_related("currency", "group")
        .order_by("group", "name")
    ]

    if request.method == "POST":
        formset = AccountBalanceFormSet(request.POST, initial=initial_data)
        if formset.is_valid():
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

                        current_balance = get_account_balance(account)
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
                                date=timezone.localdate(timezone.now()),
                                reference_date=timezone.localdate(
                                    timezone.now()
                                ).replace(day=1),
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
        request, "accounts/fragments/account_reconciliation.html", {"form": formset}
    )
