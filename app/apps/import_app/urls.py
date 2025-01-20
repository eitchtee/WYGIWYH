from django.urls import path
import apps.import_app.views as views

urlpatterns = [
    path("import/", views.import_view, name="import"),
    path(
        "import/profiles/",
        views.import_profile_index,
        name="import_profiles_index",
    ),
    path(
        "import/profiles/list/",
        views.import_profile_list,
        name="import_profiles_list",
    ),
    path(
        "import/profiles/add/",
        views.import_profile_add,
        name="import_profiles_add",
    ),
    path(
        "import/profiles/<int:profile_id>/edit/",
        views.import_profile_edit,
        name="import_profile_edit",
    ),
    path(
        "import/profiles/<int:profile_id>/runs/",
        views.import_run_add,
        name="import_profile_runs_index",
    ),
    path(
        "import/profiles/<int:profile_id>/runs/list/",
        views.import_run_add,
        name="import_profile_runs_list",
    ),
    path(
        "import/profiles/<int:profile_id>/runs/add/",
        views.import_run_add,
        name="import_run_add",
    ),
]
