from rest_framework.permissions import (
    SAFE_METHODS,
    BasePermission,
    DjangoModelPermissions,
)
from django.conf import settings


class NotInDemoMode(BasePermission):
    def has_permission(self, request, view):
        if settings.DEMO and not request.user.is_superuser:
            return False
        else:
            return True


class SharedObjectPermission(BasePermission):
    """Object-level ownership check for SharedObject-backed viewsets.

    DjangoModelPermissions is model-level: a user holding ``change_account``
    may write any object the viewset's queryset returns, and for SharedObject
    that queryset includes other people's public and shared-with-them objects.
    Sharing grants read access only, so writes are restricted to the owner
    here as well.

    Set ``shared_object_via`` on the viewset when the governing SharedObject is
    reached through a relation (e.g. ``"strategy"`` for a DCA entry).
    """

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True

        guard = obj
        via = getattr(view, "shared_object_via", None)
        for attr in via.split(".") if via else []:
            guard = getattr(guard, attr)

        return guard.is_editable_by(request.user)


#: Default permissions plus the object-level ownership check. Assigning
#: ``permission_classes`` replaces the defaults, so they are repeated here.
SHARED_OBJECT_PERMISSIONS = [
    NotInDemoMode,
    DjangoModelPermissions,
    SharedObjectPermission,
]
