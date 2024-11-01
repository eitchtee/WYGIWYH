from django.urls import path

from . import views

urlpatterns = [
    path("yearly/currency/", views.index_by_currency, name="yearly_index_currency"),
    path("yearly/account/", views.index_by_account, name="yearly_index_account"),
    path(
        "yearly/currency/<int:year>/",
        views.yearly_overview_by_currency,
        name="yearly_overview_currency",
    ),
    path(
        "yearly/account/<int:year>/",
        views.yearly_overview_by_account,
        name="yearly_overview_account",
    ),
]
