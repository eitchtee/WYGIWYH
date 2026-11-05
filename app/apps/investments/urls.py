from django.urls import path

from . import views

urlpatterns = [
    path("investments/", views.investments_index, name="investments_index"),
    path("investments/list/", views.investments_list, name="investments_list"),
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
