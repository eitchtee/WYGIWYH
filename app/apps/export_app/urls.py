from django.urls import path
import apps.export_app.views as views

urlpatterns = [
    path("export/", views.export, name="export"),
]
