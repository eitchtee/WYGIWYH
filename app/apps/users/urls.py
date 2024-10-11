from django.urls import path

from . import views

urlpatterns = [
    path("login/", views.UserLoginView.as_view(), name="login"),
    # path("login/fallback/", views.UserLoginView.as_view(), name="fallback_login"),
    path("logout/", views.logout_view, name="logout"),
    path(
        "user/toggle-amount-visibility/",
        views.toggle_amount_visibility,
        name="toggle_amount_visibility",
    ),
    path(
        "user/settings/",
        views.update_settings,
        name="user_settings",
    ),
]
