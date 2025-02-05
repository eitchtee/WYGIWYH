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
    path(
        "automatic-exchange-rates/",
        views.exchange_rates_services_index,
        name="automatic_exchange_rates_index",
    ),
    path(
        "automatic-exchange-rates/list/",
        views.exchange_rates_services_list,
        name="automatic_exchange_rates_list",
    ),
    path(
        "automatic-exchange-rates/add/",
        views.exchange_rate_service_add,
        name="automatic_exchange_rate_add",
    ),
    path(
        "automatic-exchange-rates/force-fetch/",
        views.exchange_rate_service_force_fetch,
        name="automatic_exchange_rate_force_fetch",
    ),
    path(
        "automatic-exchange-rates/<int:pk>/edit/",
        views.exchange_rate_service_edit,
        name="automatic_exchange_rate_edit",
    ),
    path(
        "automatic-exchange-rates/<int:pk>/delete/",
        views.exchange_rate_service_delete,
        name="automatic_exchange_rate_delete",
    ),
]
