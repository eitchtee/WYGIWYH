from django.urls import path

from . import views

urlpatterns = [
    path("yearly/", views.index, name="yearly_index"),
    path(
        "yearly/<int:year>/",
        views.yearly_overview,
        name="yearly_overview",
    ),
]
