from django.urls import path

from . import views

urlpatterns = [
    path(
        "tools/unit-price-calculator/",
        views.unit_price_calculator,
        name="unit_price_calculator",
    ),
]
