from django.urls import path

from . import views

urlpatterns = [
    path("bank-sync/", views.bank_sync_index, name="bank_sync_index"),
    path("bank-sync/list/", views.bank_sync_list, name="bank_sync_list"),
    path("bank-sync/add/", views.bank_sync_add, name="bank_sync_add"),
    path("bank-sync/<int:pk>/edit/", views.bank_sync_edit, name="bank_sync_edit"),
    path(
        "bank-sync/<int:pk>/delete/", views.bank_sync_delete, name="bank_sync_delete"
    ),
    path(
        "bank-sync/<int:pk>/accounts/",
        views.bank_sync_accounts,
        name="bank_sync_accounts",
    ),
    path(
        "bank-sync/<int:pk>/sync/", views.bank_sync_sync_now, name="bank_sync_sync_now"
    ),
]
