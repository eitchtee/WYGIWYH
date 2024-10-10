from django.urls import path
import apps.transactions.views as views

urlpatterns = [
    path(
        "transaction/<int:transaction_id>/pay",
        views.transaction_pay,
        name="transaction_pay",
    ),
    path(
        "transaction/<int:transaction_id>/delete",
        views.transaction_delete,
        name="transaction_delete",
    ),
    path(
        "transaction/<int:transaction_id>/edit",
        views.transaction_edit,
        name="transaction_edit",
    ),
    path(
        "transaction/add",
        views.transaction_add,
        name="transaction_add",
    ),
    path(
        "transactions/transfer",
        views.transactions_transfer,
        name="transactions_transfer",
    ),
    path(
        "transactions/installments/add/",
        views.AddInstallmentPlanView.as_view(),
        name="installments_add",
    ),
    path("tags/", views.tag_list, name="tags_list"),
    path("tags/add/", views.tag_add, name="tag_add"),
    path(
        "tags/<int:tag_id>/edit/",
        views.tag_edit,
        name="tag_edit",
    ),
    path(
        "tags/<int:tag_id>/delete/",
        views.tag_delete,
        name="tag_delete",
    ),
    path("categories/", views.categories_list, name="categories_list"),
    path("categories/add/", views.category_add, name="category_add"),
    path(
        "categories/<int:category_id>/edit/",
        views.category_edit,
        name="category_edit",
    ),
    path(
        "categories/<int:category_id>/delete/",
        views.category_delete,
        name="category_delete",
    ),
]
