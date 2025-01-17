from django.urls import path
import apps.import_app.views as views

urlpatterns = [
    path("import/", views.ImportRunCreateView.as_view(), name="import"),
]
