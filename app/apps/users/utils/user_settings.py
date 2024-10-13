from django.contrib.auth import get_user_model
from apps.users.models import UserSettings


User = get_user_model()


def ensure_user_settings(user):
    """
    Check if the given user has a UserSettings model.
    If not, create one.
    """
    if not hasattr(user, "settings"):
        UserSettings.objects.create(user=user)

    return user.settings
