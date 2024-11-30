from django.urls import path

from . import views

urlpatterns = [
    path("currencies/", views.currencies_index, name="currencies_index"),
    path("currencies/list/", views.currencies_list, name="currencies_list"),
    path("currencies/add/", views.currency_add, name="currency_add"),
    path(
        "currencies/<int:pk>/edit/",
        views.currency_edit,
        name="currency_edit",
    ),
    path(
        "currencies/<int:pk>/delete/",
        views.currency_delete,
        name="currency_delete",
    ),
    path("exchange-rates/", views.exchange_rates_index, name="exchange_rates_index"),
    path("exchange-rates/list/", views.exchange_rates_list, name="exchange_rates_list"),
    path(
        "exchange-rates/pair/",
        views.exchange_rates_list_pair,
        name="exchange_rates_list_pair",
    ),
    path("exchange-rates/add/", views.exchange_rate_add, name="exchange_rate_add"),
    path(
        "exchange-rates/<int:pk>/edit/",
        views.exchange_rate_edit,
        name="exchange_rate_edit",
    ),
    path(
        "exchange-rates/<int:pk>/delete/",
        views.exchange_rate_delete,
        name="exchange_rate_delete",
    ),
]
