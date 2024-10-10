from django.urls import path

from . import views

urlpatterns = [
    path("monthly/", views.index, name="monthly_index"),
    path("", views.index, name="monthly_index"),
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
        "available_dates/",
        views.month_year_picker,
        name="available_dates",
    ),
]
