import datetime
from copy import deepcopy

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, When, Case, Value, IntegerField
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext_lazy as _, ngettext_lazy
from django.views.decorators.http import require_http_methods

from apps.common.decorators.htmx import only_htmx
from apps.rules.signals import transaction_created, transaction_updated
from apps.transactions.filters import TransactionsFilter
from apps.transactions.forms import (
    TransactionForm,
    TransferForm,
    BulkEditTransactionForm,
)
from apps.transactions.models import Transaction
from apps.transactions.utils.calculations import (
    calculate_currency_totals,
    calculate_account_totals,
    calculate_percentage_distribution,
)
from apps.transactions.utils.default_ordering import default_order


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def transaction_add(request):
    month = int(request.GET.get("month", timezone.localdate(timezone.now()).month))
    year = int(request.GET.get("year", timezone.localdate(timezone.now()).year))
    transaction_type = Transaction.Type(request.GET.get("type", "IN"))

    now = timezone.localdate(timezone.now())
    expected_date = datetime.datetime(
        day=now.day if month == now.month and year == now.year else 1,
        month=month,
        year=year,
    ).date()

    update = False

    if request.method == "POST":
        form = TransactionForm(request.POST)
        if form.is_valid():
            saved_instance = form.save()
            messages.success(request, _("Transaction added successfully"))

            if "submit" in request.POST:
                return HttpResponse(
                    status=204,
                    headers={"HX-Trigger": "updated, hide_offcanvas"},
                )
            elif "submit_and_another" in request.POST:
                form = TransactionForm(
                    initial={
                        "date": expected_date,
                        "type": transaction_type,
                    },
                )
                update = True
            elif "submit_and_similar" in request.POST:
                initial_data = {}

                # Define fields to copy from the SAVED instance
                direct_fields_to_copy = [
                    "account",  # ForeignKey -> will copy the ID
                    "type",  # ChoiceField -> will copy the value
                    "is_paid",  # BooleanField -> will copy True/False
                    "date",  # DateField -> will copy the date object
                    "reference_date",  # DateField -> will copy the date object
                    "amount",  # DecimalField -> will copy the decimal
                    "description",  # CharField -> will copy the string
                    "notes",  # TextField -> will copy the string
                    "category",  # ForeignKey -> will copy the ID
                ]
                m2m_fields_to_copy = [
                    "tags",  # ManyToManyField -> will copy list of IDs
                    "entities",  # ManyToManyField -> will copy list of IDs
                ]

                # Copy direct fields from the saved instance
                for field_name in direct_fields_to_copy:
                    value = getattr(saved_instance, field_name, None)
                    if value is not None:
                        # Handle ForeignKey: use the pk
                        if hasattr(value, "pk"):
                            initial_data[field_name] = value.pk
                        # Handle Date/DateTime/Decimal/Boolean/etc.: use the Python object directly
                        else:
                            initial_data[field_name] = (
                                value  # This correctly handles date objects!
                            )

                # Copy M2M fields: provide a list of related object pks
                for field_name in m2m_fields_to_copy:
                    m2m_manager = getattr(saved_instance, field_name)
                    initial_data[field_name] = list(
                        m2m_manager.values_list("name", flat=True)
                    )

                # Create a new form instance pre-filled with the correctly typed initial data
                form = TransactionForm(initial=initial_data)
                update = True  # Signal HTMX to update the form area

    else:
        form = TransactionForm(
            initial={
                "date": expected_date,
                "type": transaction_type,
            },
        )

    response = render(
        request,
        "transactions/fragments/add.html",
        {"form": form},
    )
    if update:
        response["HX-Trigger"] = "updated"

    return response


@login_required
@require_http_methods(["GET", "POST"])
def transaction_simple_add(request):
    month = int(request.GET.get("month", timezone.localdate(timezone.now()).month))
    year = int(request.GET.get("year", timezone.localdate(timezone.now()).year))
    transaction_type = Transaction.Type(request.GET.get("type", "IN"))

    now = timezone.localdate(timezone.now())
    expected_date = datetime.datetime(
        day=now.day if month == now.month and year == now.year else 1,
        month=month,
        year=year,
    ).date()

    if request.method == "POST":
        form = TransactionForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("Transaction added successfully"))

        form = TransactionForm(
            initial={
                "date": expected_date,
                "type": transaction_type,
            },
        )

    else:
        form = TransactionForm(
            initial={
                "date": expected_date,
                "type": transaction_type,
            },
        )

    return render(
        request,
        "transactions/pages/add.html",
        {"form": form},
    )


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def transaction_edit(request, transaction_id, **kwargs):
    transaction = get_object_or_404(Transaction, id=transaction_id)

    if request.method == "POST":
        form = TransactionForm(request.POST, instance=transaction)
        if form.is_valid():
            form.save()
            messages.success(request, _("Transaction updated successfully"))

            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "updated, hide_offcanvas"},
            )
    else:
        form = TransactionForm(instance=transaction)

    return render(
        request,
        "transactions/fragments/edit.html",
        {"form": form, "transaction": transaction},
    )


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def transactions_bulk_edit(request):
    # Get selected transaction IDs from the URL parameter
    transaction_ids = request.GET.getlist("transactions") or request.POST.getlist(
        "transactions"
    )
    # Load the selected transactions
    transactions = Transaction.objects.filter(id__in=transaction_ids)
    count = transactions.count()

    if request.method == "POST":
        form = BulkEditTransactionForm(request.POST)
        if form.is_valid():
            # Apply changes from the form to all selected transactions
            for transaction in transactions:
                for field_name, value in form.cleaned_data.items():
                    if value or isinstance(
                        value, bool
                    ):  # Only update fields that have been filled in the form
                        if field_name == "tags":
                            transaction.tags.set(value)
                        elif field_name == "entities":
                            transaction.entities.set(value)
                        else:
                            setattr(transaction, field_name, value)

                transaction.save()
                transaction_updated.send(sender=transaction)

            messages.success(
                request,
                ngettext_lazy(
                    "%(count)s transaction updated successfully",
                    "%(count)s transactions updated successfully",
                    count,
                )
                % {"count": count},
            )
            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "updated, hide_offcanvas"},
            )
    else:
        form = BulkEditTransactionForm(initial={"is_paid": None, "type": None})

    context = {
        "form": form,
        "transactions": transactions,
    }
    return render(request, "transactions/fragments/bulk_edit.html", context)


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def transaction_clone(request, transaction_id, **kwargs):
    transaction = get_object_or_404(Transaction, id=transaction_id)
    new_transaction = deepcopy(transaction)
    new_transaction.pk = None
    new_transaction.installment_plan = None
    new_transaction.installment_id = None
    new_transaction.recurring_transaction = None
    new_transaction.internal_id = None
    new_transaction.save()

    new_transaction.tags.add(*transaction.tags.all())
    new_transaction.entities.add(*transaction.entities.all())

    messages.success(request, _("Transaction duplicated successfully"))

    transaction_created.send(sender=transaction)

    # THIS HAS BEEN DISABLE DUE TO HTMX INCOMPATIBILITY
    # SEE https://github.com/bigskysoftware/htmx/issues/3115 and https://github.com/bigskysoftware/htmx/issues/2706

    # if request.GET.get("edit") == "true":
    #     return HttpResponse(
    #         status=200,
    #         headers={
    #             "HX-Trigger": "updated",
    #             "HX-Push-Url": "false",
    #             "HX-Location": json.dumps(
    #                 {
    #                     "path": reverse(
    #                         "transaction_edit",
    #                         kwargs={"transaction_id": new_transaction.id},
    #                     ),
    #                     "target": "#generic-offcanvas",
    #                     "swap": "innerHTML",
    #                 }
    #             ),
    #         },
    #     )
    # else:
    #     transaction_created.send(sender=transaction)

    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "updated"},
    )


@only_htmx
@login_required
@require_http_methods(["DELETE"])
def transaction_delete(request, transaction_id, **kwargs):
    transaction = get_object_or_404(Transaction.all_objects, id=transaction_id)

    transaction.delete()

    messages.success(request, _("Transaction deleted successfully"))

    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "updated"},
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def transaction_undelete(request, transaction_id, **kwargs):
    transaction = get_object_or_404(Transaction.deleted_objects, id=transaction_id)

    transaction.deleted = False
    transaction.deleted_at = None
    transaction.save()

    messages.success(request, _("Transaction restored successfully"))

    return HttpResponse(
        status=204,
        headers={"HX-Trigger": "updated"},
    )


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def transactions_transfer(request):
    month = int(request.GET.get("month", timezone.localdate(timezone.now()).month))
    year = int(request.GET.get("year", timezone.localdate(timezone.now()).year))

    now = timezone.localdate(timezone.now())
    expected_date = datetime.datetime(
        day=now.day if month == now.month and year == now.year else 1,
        month=month,
        year=year,
    ).date()

    if request.method == "POST":
        form = TransferForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("Transfer added successfully"))
            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "updated, hide_offcanvas"},
            )
    else:
        form = TransferForm(
            initial={
                "reference_date": expected_date,
                "date": expected_date,
            },
        )

    return render(request, "transactions/fragments/transfer.html", {"form": form})


@only_htmx
@login_required
@require_http_methods(["GET"])
def transaction_pay(request, transaction_id):
    transaction = get_object_or_404(Transaction, pk=transaction_id)
    new_is_paid = False if transaction.is_paid else True
    transaction.is_paid = new_is_paid
    transaction.save()
    transaction_updated.send(sender=transaction)

    response = render(
        request,
        "transactions/fragments/item.html",
        context={"transaction": transaction, **request.GET},
    )
    response.headers["HX-Trigger"] = (
        f'{"paid" if new_is_paid else "unpaid"}, selective_update'
    )
    return response


@only_htmx
@login_required
@require_http_methods(["GET"])
def transaction_mute(request, transaction_id):
    transaction = get_object_or_404(Transaction, pk=transaction_id)

    new_mute = False if transaction.mute else True
    transaction.mute = new_mute
    transaction.save()
    transaction_updated.send(sender=transaction)

    response = render(
        request,
        "transactions/fragments/item.html",
        context={"transaction": transaction, **request.GET},
    )
    response.headers["HX-Trigger"] = "selective_update"
    return response


@login_required
@require_http_methods(["GET"])
def transaction_all_index(request):
    order = request.session.get("all_transactions_order", "default")
    summary_tab = request.session.get("transaction_all_summary_tab", "currency")

    f = TransactionsFilter(request.GET)
    return render(
        request,
        "transactions/pages/transactions.html",
        {"filter": f, "order": order, "summary_tab": summary_tab},
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def transaction_all_list(request):
    order = request.session.get("all_transactions_order", "default")

    if "order" in request.GET:
        order = request.GET["order"]
        if order != request.session.get("all_transactions_order", "default"):
            request.session["all_transactions_order"] = order

    transactions = Transaction.objects.prefetch_related(
        "account",
        "account__group",
        "category",
        "tags",
        "account__exchange_currency",
        "account__currency",
        "installment_plan",
        "entities",
        "dca_expense_entries",
        "dca_income_entries",
    ).all()

    transactions = default_order(transactions, order=order)

    f = TransactionsFilter(request.GET, queryset=transactions)

    page_number = request.GET.get("page", 1)
    paginator = Paginator(f.qs, 100)
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "transactions/fragments/list_all.html",
        {
            "page_obj": page_obj,
            "paginator": paginator,
        },
    )


@only_htmx
@login_required
@require_http_methods(["GET"])
def transaction_all_summary(request):
    transactions = Transaction.objects.prefetch_related(
        "account",
        "account__group",
        "category",
        "tags",
        "account__exchange_currency",
        "account__currency",
        "installment_plan",
        "entities",
        "dca_expense_entries",
        "dca_income_entries",
    ).all()

    f = TransactionsFilter(request.GET, queryset=transactions)

    currency_data = calculate_currency_totals(f.qs.all(), ignore_empty=True)
    currency_percentages = calculate_percentage_distribution(currency_data)
    account_data = calculate_account_totals(transactions_queryset=f.qs.all())
    account_percentages = calculate_percentage_distribution(account_data)

    context = {
        "currency_data": currency_data,
        "currency_percentages": currency_percentages,
        "account_data": account_data,
        "account_percentages": account_percentages,
    }

    return render(request, "transactions/fragments/summary.html", context)


@only_htmx
@login_required
@require_http_methods(["GET"])
def transaction_all_account_summary(request):
    transactions = Transaction.objects.prefetch_related(
        "account",
        "account__group",
        "category",
        "tags",
        "account__exchange_currency",
        "account__currency",
        "installment_plan",
        "entities",
        "dca_expense_entries",
        "dca_income_entries",
    ).all()

    f = TransactionsFilter(request.GET, queryset=transactions)

    account_data = calculate_account_totals(transactions_queryset=f.qs.all())
    account_percentages = calculate_percentage_distribution(account_data)

    context = {
        "account_data": account_data,
        "account_percentages": account_percentages,
    }

    return render(request, "transactions/fragments/all_account_summary.html", context)


@only_htmx
@login_required
@require_http_methods(["GET"])
def transaction_all_currency_summary(request):
    transactions = Transaction.objects.prefetch_related(
        "account",
        "account__group",
        "category",
        "tags",
        "account__exchange_currency",
        "account__currency",
        "installment_plan",
        "entities",
        "dca_expense_entries",
        "dca_income_entries",
    ).all()

    f = TransactionsFilter(request.GET, queryset=transactions)

    currency_data = calculate_currency_totals(f.qs.all(), ignore_empty=True)
    currency_percentages = calculate_percentage_distribution(currency_data)

    context = {
        "currency_data": currency_data,
        "currency_percentages": currency_percentages,
    }

    return render(request, "transactions/fragments/all_currency_summary.html", context)


@login_required
@require_http_methods(["GET"])
def transaction_all_summary_select(request, selected):
    request.session["transaction_all_summary_tab"] = selected

    return HttpResponse(
        status=204,
    )


@login_required
@require_http_methods(["GET"])
def transactions_trash_can_index(request):
    return render(request, "transactions/pages/trash.html")


@only_htmx
@login_required
@require_http_methods(["GET"])
def transactions_trash_can_list(request):
    transactions = Transaction.deleted_objects.prefetch_related(
        "account",
        "account__group",
        "category",
        "tags",
        "account__exchange_currency",
        "account__currency",
        "installment_plan",
        "entities",
        "entities",
        "dca_expense_entries",
        "dca_income_entries",
    ).all()

    return render(
        request,
        "transactions/fragments/trash_list.html",
        {"transactions": transactions},
    )


@login_required
@require_http_methods(["GET"])
def get_recent_transactions(request, filter_type=None):
    """Return the 100 most recent non-deleted transactions with optional search."""
    # Get search term from query params
    search_term = request.GET.get("q", "").strip()

    today = timezone.localdate(timezone.now())
    yesterday = today - timezone.timedelta(days=1)
    tomorrow = today + timezone.timedelta(days=1)

    # Base queryset with selected fields
    queryset = (
        Transaction.objects.filter(deleted=False)
        .annotate(
            date_order=Case(
                When(date=today, then=Value(0)),
                When(date=tomorrow, then=Value(1)),
                When(date=yesterday, then=Value(2)),
                When(date__gt=tomorrow, then=Value(3)),
                When(date__lt=yesterday, then=Value(4)),
                default=Value(5),
                output_field=IntegerField(),
            )
        )
        .select_related("account", "category")
        .order_by("date_order", "date", "id")
    )

    if filter_type:
        if filter_type == "expenses":
            queryset = queryset.filter(type=Transaction.Type.EXPENSE)
        elif filter_type == "income":
            queryset = queryset.filter(type=Transaction.Type.INCOME)

    # Apply search if provided
    if search_term:
        queryset = queryset.filter(
            Q(description__icontains=search_term)
            | Q(notes__icontains=search_term)
            | Q(internal_note__icontains=search_term)
            | Q(tags__name__icontains=search_term)
            | Q(category__name__icontains=search_term)
        )

    # Prepare data for JSON response
    data = []
    for t in queryset:
        data.append({"text": str(t), "value": str(t.id)})

    return JsonResponse(data, safe=False)
