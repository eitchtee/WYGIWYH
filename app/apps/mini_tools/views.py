from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.common.widgets.decimal import convert_to_decimal
from apps.currencies.models import Currency
from apps.currencies.utils.convert import convert
from apps.mini_tools.forms import CurrencyConverterForm


@login_required
def unit_price_calculator(request):
    return render(request, "mini_tools/unit_price_calculator.html")


@login_required
def currency_converter(request):
    form = CurrencyConverterForm()
    return render(
        request,
        "mini_tools/currency_converter/currency_converter.html",
        context={"form": form},
    )


@login_required
def currency_converter_convert(request):
    from_value = request.GET.get("from_value")
    from_currency = request.GET.get("from_currency")
    to_currency = request.GET.get("to_currency")

    if from_currency:
        from_currency = Currency.objects.filter(id=from_currency).first()
    if to_currency:
        to_currency = Currency.objects.filter(id=to_currency).first()
    if from_value:
        from_value = convert_to_decimal(from_value)

    if from_currency and to_currency and from_value:
        converted_amount, prefix, suffix, decimal_places = convert(
            amount=from_value,
            from_currency=from_currency,
            to_currency=to_currency,
        )
    else:
        converted_amount = None
        prefix = ""
        suffix = ""
        decimal_places = 0

    return render(
        request,
        "mini_tools/currency_converter/converted_value.html",
        context={
            "converted_amount": converted_amount,
            "prefix": prefix,
            "suffix": suffix,
            "decimal_places": decimal_places,
        },
    )
