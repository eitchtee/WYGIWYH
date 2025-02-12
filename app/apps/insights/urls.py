from django.urls import path

from . import views

urlpatterns = [
    path("insights/", views.index, name="insights_index"),
    path("insights/sankey/", views.sankey, name="sankey"),
]
