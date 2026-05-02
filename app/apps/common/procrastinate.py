import functools
import inspect

import procrastinate
from django.db import close_old_connections


_CONNECTION_CLEANUP_WRAPPED = "_wygiwyh_connection_cleanup_wrapped"


def _wrap_task_with_django_connection_cleanup(task):
    if getattr(task.func, _CONNECTION_CLEANUP_WRAPPED, False):
        return

    func = task.func

    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def async_wrapped(*args, **kwargs):
            close_old_connections()
            try:
                return await func(*args, **kwargs)
            finally:
                close_old_connections()

        wrapped = async_wrapped
    else:

        @functools.wraps(func)
        def sync_wrapped(*args, **kwargs):
            close_old_connections()
            try:
                return func(*args, **kwargs)
            finally:
                close_old_connections()

        wrapped = sync_wrapped

    setattr(wrapped, _CONNECTION_CLEANUP_WRAPPED, True)
    task.func = wrapped


def on_app_ready(app: procrastinate.App):
    """This function is ran upon procrastinate initialization."""
    for task in set(app.tasks.values()):
        _wrap_task_with_django_connection_cleanup(task)
