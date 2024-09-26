from django.urls import path

from . import views

urlpatterns = [
    path("login/", views.UserLoginView.as_view(), name="login"),
    # path("login/fallback/", views.UserLoginView.as_view(), name="fallback_login"),
    path("logout/", views.logout_view, name="logout"),
]
