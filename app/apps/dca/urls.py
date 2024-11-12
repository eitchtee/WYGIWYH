from django.urls import path
from . import views


urlpatterns = [
    path("dca/", views.strategy_list, name="strategy_list"),
    path("dca/<int:pk>/", views.strategy_detail, name="strategy_detail"),
    # Add more URLs for CRUD operations
]
