from django.urls import path

from . import views

urlpatterns = [
    path(
        "toasts/",
        views.toasts,
        name="toasts",
    ),
]
