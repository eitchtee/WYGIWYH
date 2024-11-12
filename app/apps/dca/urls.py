from django.urls import path
from . import views


urlpatterns = [
    path("dca/", views.strategy_index, name="dca_strategy_index"),
    path("dca/list/", views.strategy_list, name="dca_strategy_list"),
    path("dca/add/", views.strategy_add, name="dca_strategy_add"),
    path("dca/<int:strategy_id>/edit/", views.strategy_edit, name="dca_strategy_edit"),
    path(
        "dca/<int:strategy_id>/delete/",
        views.strategy_delete,
        name="dca_strategy_delete",
    ),
    path(
        "dca/<int:strategy_id>/",
        views.strategy_detail_index,
        name="dca_strategy_detail_index",
    ),
    path(
        "dca/<int:strategy_id>/details/",
        views.strategy_detail,
        name="dca_strategy_detail",
    ),
    path("dca/<int:strategy_id>/add/", views.strategy_entry_add, name="dca_entry_add"),
    path(
        "dca/<int:strategy_id>/<int:entry_id>/edit/",
        views.strategy_entry_edit,
        name="dca_entry_edit",
    ),
    path(
        "dca/<int:strategy_id>/<int:entry_id>/delete/",
        views.strategy_entry_delete,
        name="dca_entry_delete",
    ),
]
