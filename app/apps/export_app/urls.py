from django.urls import path
import apps.export_app.views as views

urlpatterns = [
    path("export/", views.export_index, name="export_index"),
    path("export/form/", views.export_form, name="export_form"),
    path("export/restore/", views.import_form, name="restore_form"),
]
