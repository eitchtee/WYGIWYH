from functools import wraps

from django.conf import settings
from django.core.exceptions import PermissionDenied


def disabled_on_demo(view):
    @wraps(view)
    def _view(request, *args, **kwargs):
        if settings.DEMO and not request.user.is_superuser:
            raise PermissionDenied

        return view(request, *args, **kwargs)

    return _view
