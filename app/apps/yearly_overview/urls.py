from django.urls import path

from . import views

urlpatterns = [
    path("yearly/", views.index, name="yearly_index"),
    path("yearly/currency/", views.index_by_currency, name="yearly_index_currency"),
    path("yearly/account/", views.index_by_account, name="yearly_index_account"),
    path(
        "yearly/currency/<int:year>/",
        views.index_yearly_overview_by_currency,
        name="yearly_overview_currency",
    ),
    path(
        "yearly-overview/<int:year>/currency/data/",
        views.yearly_overview_by_currency,
        name="yearly_overview_currency_data",
    ),
    path(
        "yearly/account/<int:year>/",
        views.index_yearly_overview_by_account,
        name="yearly_overview_account",
    ),
    path(
        "yearly-overview/<int:year>/account/data/",
        views.yearly_overview_by_account,
        name="yearly_overview_account_data",
    ),
]
