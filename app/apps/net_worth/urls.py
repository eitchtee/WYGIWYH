from django.urls import path

from . import views

urlpatterns = [
    path("net-worth/current/", views.net_worth_current, name="net_worth_current"),
    path("net-worth/projected/", views.net_worth_projected, name="net_worth_projected"),
]
