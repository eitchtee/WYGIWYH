from rest_framework.permissions import BasePermission
from django.conf import settings


class NotInDemoMode(BasePermission):
    def has_permission(self, request, view):
        if settings.DEMO and not request.user.is_superuser:
            return False
        else:
            return True
