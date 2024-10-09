from django.urls import path

from . import views

urlpatterns = [
    path("net-worth/", views.net_worth_main, name="net_worth"),
]
