from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path(
        "transactions/<int:month>/<int:year>/",
        views.transactions_overview,
        name="transactions_overview",
    ),
    path(
        "transactions/<int:month>/<int:year>/list/",
        views.transactions_list,
        name="transactions_list",
    ),
    path(
        "transactions/<int:month>/<int:year>/summary/",
        views.monthly_summary,
        name="monthly_summary",
    ),
    path(
        "transaction/<int:transaction_id>/pay",
        views.transaction_pay,
        name="transaction_pay",
    ),
    path(
        "transaction/<int:transaction_id>/delete",
        views.transaction_delete,
        name="transaction_delete",
    ),
    path(
        "transaction/<int:transaction_id>/edit",
        views.transaction_edit,
        name="transaction_edit",
    ),
    path(
        "transaction/add",
        views.transaction_add,
        name="transaction_add",
    ),
    path(
        "available_dates/",
        views.month_year_picker,
        name="available_dates",
    ),
]
