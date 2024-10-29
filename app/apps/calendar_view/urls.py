from django.urls import path

from . import views

urlpatterns = [
    path("calendar/", views.index, name="calendar_index"),
    path(
        "calendar/<int:month>/<int:year>/list/",
        views.calendar_list,
        name="calendar_list",
    ),
    path(
        "calendar/<int:day>/<int:month>/<int:year>/transactions/",
        views.calendar_transactions_list,
        name="calendar_transactions_list",
    ),
    path(
        "calendar/<int:month>/<int:year>/",
        views.calendar,
        name="calendar",
    ),
    # path(
    #     "calendar/available_dates/",
    #     views.month_year_picker,
    #     name="available_dates",
    # ),
]
