from django.urls import path

from . import views

urlpatterns = [
    path("insights/sankey/", views.sankey, name="sankey"),
]
