from django.urls import path

from . import views

urlpatterns = [
    path("insights/", views.index, name="insights_index"),
    path(
        "insights/sankey/account/",
        views.sankey_by_account,
        name="insights_sankey_by_account",
    ),
    path(
        "insights/sankey/currency/",
        views.sankey_by_currency,
        name="insights_sankey_by_currency",
    ),
]
