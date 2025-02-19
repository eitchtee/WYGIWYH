import zipfile
from io import BytesIO

from django.http import HttpResponse
from django.shortcuts import render

from apps.export_app.forms import ExportForm
from apps.export_app.resources.accounts import AccountResource
from apps.export_app.resources.transactions import (
    TransactionResource,
    TransactionTagResource,
    TransactionEntityResource,
    TransactionCategoyResource,
)
from apps.export_app.resources.currencies import (
    CurrencyResource,
    ExchangeRateResource,
    ExchangeRateServiceResource,
)


# Create your views here.
def export_index(request):
    dataset = TransactionResource().export()
    print(dataset.csv)


def export_form(request):
    if request.method == "POST":
        form = ExportForm(request.POST)
        if form.is_valid():
            zip_buffer = BytesIO()

            export_accounts = form.cleaned_data.get("accounts", False)
            export_currencies = form.cleaned_data.get("currencies", False)
            export_transactions = form.cleaned_data.get("transactions", False)
            export_categories = form.cleaned_data.get("categories", False)
            export_tags = form.cleaned_data.get("tags", False)
            export_entities = form.cleaned_data.get("entities", False)
            export_exchange_rates_services = form.cleaned_data.get(
                "exchange_rates_services", False
            )
            export_exchange_rates = form.cleaned_data.get("exchange_rates", False)

            exports = []
            if export_accounts:
                exports.append((AccountResource().export(), "accounts"))
            if export_currencies:
                exports.append((CurrencyResource().export(), "currencies"))
            if export_transactions:
                exports.append((TransactionResource().export(), "transactions"))
            if export_tags:
                exports.append((TransactionTagResource().export(), "transactions_tags"))
            if export_entities:
                exports.append(
                    (TransactionEntityResource().export(), "transactions_entities")
                )
            if export_categories:
                exports.append(
                    (TransactionCategoyResource().export(), "transactions_categories")
                )
            if export_exchange_rates_services:
                exports.append(
                    (ExchangeRateServiceResource().export(), "automatic_exchange_rates")
                )
            if export_exchange_rates:
                exports.append((ExchangeRateResource().export(), "exchange_rates"))

            if len(exports) >= 2:
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                    for dataset, name in exports:
                        zip_file.writestr(f"{name}.csv", dataset.csv)

                response = HttpResponse(
                    zip_buffer.getvalue(), content_type="application/zip"
                )
                response["Content-Disposition"] = f'attachment; filename="export.zip"'
                return response
            else:
                dataset, name = exports[0]

                response = HttpResponse(
                    dataset.csv,
                    content_type="text/csv",
                )
                response["Content-Disposition"] = f'attachment; filename="{name}.csv"'
                return response

    else:
        form = ExportForm()

    return render(request, "export_app/pages/form.html", context={"form": form})
