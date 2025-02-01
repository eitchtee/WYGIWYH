from django.urls import path

from . import views

urlpatterns = [
    path("monthly/", views.index, name="monthly_index"),
    path(
        "monthly/<int:month>/<int:year>/transactions/list/",
        views.transactions_list,
        name="monthly_transactions_list",
    ),
    path(
        "monthly/<int:month>/<int:year>/",
        views.monthly_overview,
        name="monthly_overview",
    ),
    path(
        "monthly/<int:month>/<int:year>/summary/",
        views.monthly_summary,
        name="monthly_summary",
    ),
    path(
        "monthly/<int:month>/<int:year>/summary/accounts/",
        views.monthly_account_summary,
        name="monthly_account_summary",
    ),
    path(
        "monthly/<int:month>/<int:year>/summary/currencies/",
        views.monthly_currency_summary,
        name="monthly_currency_summary",
    ),
    path(
        "monthly/summary/select/<str:selected>/",
        views.monthly_summary_select,
        name="monthly_summary_select",
    ),
]
