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
    path(
        "insights/category-explorer/",
        views.category_explorer_index,
        name="category_explorer_index",
    ),
    path(
        "insights/category-explorer/account/",
        views.category_sum_by_account,
        name="category_sum_by_account",
    ),
    path(
        "insights/category-explorer/currency/",
        views.category_sum_by_currency,
        name="category_sum_by_currency",
    ),
]
