from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("login/", views.UserLoginView.as_view(), name="login"),
    # path("login/fallback/", views.UserLoginView.as_view(), name="fallback_login"),
    path("logout/", views.logout_view, name="logout"),
    path(
        "user/toggle-amount-visibility/",
        views.toggle_amount_visibility,
        name="toggle_amount_visibility",
    ),
    path(
        "user/toggle-sound-playing/",
        views.toggle_sound_playing,
        name="toggle_sound_playing",
    ),
    path(
        "user/settings/",
        views.update_settings,
        name="user_settings",
    ),
    path(
        "users/",
        views.users_index,
        name="users_index",
    ),
    path(
        "users/list/",
        views.users_list,
        name="users_list",
    ),
    path(
        "user/add/",
        views.user_add,
        name="user_add",
    ),
    path(
        "user/<int:pk>/edit/",
        views.user_edit,
        name="user_edit",
    ),
]
