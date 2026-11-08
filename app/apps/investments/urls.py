from django.urls import path

from . import views

urlpatterns = [
    path("investments/", views.investments_index, name="investments_index"),
    path("investments/list/", views.investments_list, name="investments_list"),
    path("investments/charts/", views.investments_charts, name="investments_charts"),
    path(
        "investments/rebalance/",
        views.investments_rebalance,
        name="investments_rebalance",
    ),
    path(
        "investments/classes/",
        views.investment_classes_index,
        name="investment_classes_index",
    ),
    path(
        "investments/classes/list/",
        views.investment_classes_list,
        name="investment_classes_list",
    ),
    path(
        "investments/classes/add/",
        views.investment_class_add,
        name="investment_class_add",
    ),
    path(
        "investments/classes/<int:pk>/edit/",
        views.investment_class_edit,
        name="investment_class_edit",
    ),
    path(
        "investments/classes/<int:pk>/delete/",
        views.investment_class_delete,
        name="investment_class_delete",
    ),
    path(
        "investments/<int:account_id>/",
        views.investment_detail_index,
        name="investment_detail_index",
    ),
    path(
        "investments/<int:account_id>/details/",
        views.investment_detail,
        name="investment_detail",
    ),
]
