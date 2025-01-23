from django.urls import path
import apps.import_app.views as views

urlpatterns = [
    path("import/", views.import_view, name="import"),
    path(
        "import/presets/",
        views.import_presets_list,
        name="import_presets_list",
    ),
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
        "import/profiles/<int:profile_id>/delete/",
        views.import_profile_delete,
        name="import_profile_delete",
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
        "import/profiles/<int:profile_id>/runs/list/",
        views.import_runs_list,
        name="import_profile_runs_list",
    ),
    path(
        "import/profiles/<int:profile_id>/runs/<int:run_id>/log/",
        views.import_run_log,
        name="import_run_log",
    ),
    path(
        "import/profiles/<int:profile_id>/runs/<int:run_id>/delete/",
        views.import_run_delete,
        name="import_run_delete",
    ),
    path(
        "import/profiles/<int:profile_id>/runs/add/",
        views.import_run_add,
        name="import_run_add",
    ),
]
