from django.urls import path

from . import views

urlpatterns = [
    path(
        "toasts/",
        views.toasts,
        name="toasts",
    ),
    path(
        "ui/month-year-picker/",
        views.month_year_picker,
        name="month_year_picker",
    ),
]
