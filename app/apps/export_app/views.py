import logging
import zipfile
from io import BytesIO

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods
from tablib import Dataset

from apps.common.decorators.htmx import only_htmx
from apps.export_app.forms import ExportForm, RestoreForm
from apps.export_app.resources.accounts import AccountResource
from apps.export_app.resources.currencies import (
    CurrencyResource,
    ExchangeRateResource,
    ExchangeRateServiceResource,
)
from apps.export_app.resources.dca import (
    DCAStrategyResource,
    DCAEntryResource,
)
from apps.export_app.resources.import_app import (
    ImportProfileResource,
)
from apps.export_app.resources.rules import (
    TransactionRuleResource,
    TransactionRuleActionResource,
    UpdateOrCreateTransactionRuleResource,
)
from apps.export_app.resources.transactions import (
    TransactionResource,
    TransactionTagResource,
    TransactionEntityResource,
    TransactionCategoyResource,
    InstallmentPlanResource,
    RecurringTransactionResource,
)
from apps.export_app.resources.users import UserResource

logger = logging.getLogger()


@login_required
@user_passes_test(lambda u: u.is_superuser)
@require_http_methods(["GET"])
def export_index(request):
    return render(request, "export_app/pages/index.html")


@login_required
@user_passes_test(lambda u: u.is_superuser)
@require_http_methods(["GET", "POST"])
def export_form(request):
    timestamp = timezone.localtime(timezone.now()).strftime("%Y-%m-%dT%H-%M-%S")

    if request.method == "POST":
        form = ExportForm(request.POST)
        if form.is_valid():
            zip_buffer = BytesIO()

            export_users = form.cleaned_data.get("users", False)
            export_accounts = form.cleaned_data.get("accounts", False)
            export_currencies = form.cleaned_data.get("currencies", False)
            export_transactions = form.cleaned_data.get("transactions", False)
            export_categories = form.cleaned_data.get("categories", False)
            export_tags = form.cleaned_data.get("tags", False)
            export_entities = form.cleaned_data.get("entities", False)
            export_installment_plans = form.cleaned_data.get("installment_plans", False)
            export_recurring_transactions = form.cleaned_data.get(
                "recurring_transactions", False
            )

            export_exchange_rates_services = form.cleaned_data.get(
                "exchange_rates_services", False
            )
            export_exchange_rates = form.cleaned_data.get("exchange_rates", False)
            export_rules = form.cleaned_data.get("rules", False)
            export_dca = form.cleaned_data.get("dca", False)
            export_import_profiles = form.cleaned_data.get("import_profiles", False)

            exports = []
            if export_users:
                exports.append((UserResource().export(), "users"))
            if export_accounts:
                exports.append((AccountResource().export(), "accounts"))
            if export_currencies:
                exports.append((CurrencyResource().export(), "currencies"))
            if export_transactions:
                exports.append((TransactionResource().export(), "transactions"))
            if export_categories:
                exports.append(
                    (TransactionCategoyResource().export(), "transactions_categories")
                )
            if export_tags:
                exports.append((TransactionTagResource().export(), "transactions_tags"))
            if export_entities:
                exports.append(
                    (TransactionEntityResource().export(), "transactions_entities")
                )
            if export_installment_plans:
                exports.append(
                    (InstallmentPlanResource().export(), "installment_plans")
                )
            if export_recurring_transactions:
                exports.append(
                    (RecurringTransactionResource().export(), "recurring_transactions")
                )
            if export_exchange_rates_services:
                exports.append(
                    (ExchangeRateServiceResource().export(), "automatic_exchange_rates")
                )
            if export_exchange_rates:
                exports.append((ExchangeRateResource().export(), "exchange_rates"))
            if export_rules:
                exports.append(
                    (TransactionRuleResource().export(), "transaction_rules")
                )
                exports.append(
                    (
                        TransactionRuleActionResource().export(),
                        "transaction_rules_actions",
                    )
                )
                exports.append(
                    (
                        UpdateOrCreateTransactionRuleResource().export(),
                        "transaction_rules_update_or_create",
                    )
                )
            if export_dca:
                exports.append((DCAStrategyResource().export(), "dca_strategies"))
                exports.append(
                    (
                        DCAEntryResource().export(),
                        "dca_entries",
                    )
                )
            if export_import_profiles:
                exports.append((ImportProfileResource().export(), "import_profiles"))

            if len(exports) >= 2:
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                    for dataset, name in exports:
                        zip_file.writestr(f"{name}.csv", dataset.csv)

                response = HttpResponse(
                    zip_buffer.getvalue(),
                    content_type="application/zip",
                    headers={
                        "HX-Trigger": "hide_offcanvas, updated",
                        "Content-Disposition": f'attachment; filename="{timestamp}_WYGIWYH_export.zip"',
                    },
                )
                return response
            elif len(exports) == 1:
                dataset, name = exports[0]

                response = HttpResponse(
                    dataset.csv,
                    content_type="text/csv",
                    headers={
                        "HX-Trigger": "hide_offcanvas, updated",
                        "Content-Disposition": f'attachment; filename="{timestamp}_WYGIWYH_export_{name}.csv"',
                    },
                )
                return response
            else:
                return HttpResponse(
                    _("You have to select at least one export"),
                )

    else:
        form = ExportForm()

    return render(request, "export_app/fragments/export.html", context={"form": form})


@only_htmx
@login_required
@user_passes_test(lambda u: u.is_superuser)
@require_http_methods(["GET", "POST"])
def import_form(request):
    if request.method == "POST":
        form = RestoreForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                process_imports(request, form.cleaned_data)
                messages.success(request, _("Data restored successfully"))
                return HttpResponse(
                    status=204,
                    headers={
                        "HX-Trigger": "hide_offcanvas, updated",
                    },
                )
            except Exception as e:
                logger.error("Error importing", exc_info=e)
                messages.error(
                    request,
                    _(
                        "There was an error restoring your data. Check the logs for more details."
                    ),
                )
    else:
        form = RestoreForm()

    response = render(request, "export_app/fragments/restore.html", {"form": form})
    response["HX-Trigger"] = "updated"
    return response


def process_imports(request, cleaned_data):
    # Define import order to handle dependencies
    import_order = [
        ("users", UserResource),
        ("currencies", CurrencyResource),
        (
            "currencies",
            CurrencyResource,
        ),  # We do a double pass because exchange_currency may not exist when currency is initially created
        ("accounts", AccountResource),
        ("transactions_categories", TransactionCategoyResource),
        ("transactions_tags", TransactionTagResource),
        ("transactions_entities", TransactionEntityResource),
        ("automatic_exchange_rates", ExchangeRateServiceResource),
        ("exchange_rates", ExchangeRateResource),
        ("installment_plans", InstallmentPlanResource),
        ("recurring_transactions", RecurringTransactionResource),
        ("transactions", TransactionResource),
        ("dca_strategies", DCAStrategyResource),
        ("dca_entries", DCAEntryResource),
        ("import_profiles", ImportProfileResource),
        ("transaction_rules", TransactionRuleResource),
        ("transaction_rules_actions", TransactionRuleActionResource),
        ("transaction_rules_update_or_create", UpdateOrCreateTransactionRuleResource),
    ]

    def import_dataset(content, resource_class, field_name):
        try:
            # Create a new resource instance
            resource = resource_class()

            # Create dataset from CSV content
            dataset = Dataset()
            dataset.load(content, format="csv")

            # Perform the import
            result = resource.import_data(
                dataset,
                dry_run=False,
                raise_errors=True,
                collect_failed_rows=True,
                use_transactions=False,
                skip_unchanged=True,
            )

            if result.has_errors():
                raise ImportError(f"Failed rows: {result.failed_dataset}")

            return result

        except Exception as e:
            logger.error(f"Error importing {field_name}: {str(e)}")
            raise ImportError(f"Error importing {field_name}: {str(e)}")

    with transaction.atomic():
        files = {}

        if zip_file := cleaned_data.get("zip_file"):
            # Process ZIP file
            with zipfile.ZipFile(zip_file) as z:
                for filename in z.namelist():
                    name = filename.replace(".csv", "")
                    with z.open(filename) as f:
                        content = f.read().decode("utf-8")

                        files[name] = content

            for field_name, resource_class in import_order:
                if field_name in files.keys():
                    content = files[field_name]
                    import_dataset(content, resource_class, field_name)
        else:
            # Process individual files
            for field_name, resource_class in import_order:
                if csv_file := cleaned_data.get(field_name):
                    content = csv_file.read().decode("utf-8")
                    import_dataset(content, resource_class, field_name)
