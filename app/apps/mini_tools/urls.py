from django.urls import path

from . import views

urlpatterns = [
    path(
        "tools/unit-price-calculator/",
        views.unit_price_calculator,
        name="unit_price_calculator",
    ),
    path(
        "tools/currency-converter/",
        views.currency_converter,
        name="currency_converter",
    ),
    path(
        "tools/currency-converter/convert/",
        views.currency_converter_convert,
        name="currency_converter_convert",
    ),
]
