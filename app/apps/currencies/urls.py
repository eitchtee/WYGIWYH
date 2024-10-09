from django.urls import path

from . import views

urlpatterns = [
    path("currencies/", views.currency_list, name="currencies_list"),
    path("currencies/add/", views.currency_add, name="currency_add"),
    path(
        "currencies/<int:pk>/edit/",
        views.currency_edit,
        name="currency_edit",
    ),
    path(
        "currencies/<int:pk>/delete/",
        views.currency_delete,
        name="currency_delete",
    ),
]
