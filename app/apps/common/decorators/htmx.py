from functools import wraps

from django.core.exceptions import PermissionDenied


def only_htmx(view):
    @wraps(view)
    def _view(request, *args, **kwargs):
        if not request.META.get("HTTP_HX_REQUEST"):
            raise PermissionDenied

        return view(request, *args, **kwargs)

    return _view
