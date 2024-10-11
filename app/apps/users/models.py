import pytz
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.contrib.auth.models import AbstractUser, Group
from django.utils.translation import gettext_lazy as _

from apps.users.managers import UserManager


class User(AbstractUser):
    username = None
    email = models.EmailField(_("E-mail"), unique=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"


class UserSettings(models.Model):
    user = models.OneToOneField(
        get_user_model(), on_delete=models.CASCADE, related_name="settings"
    )
    hide_amounts = models.BooleanField(default=False)

    language = models.CharField(
        max_length=10,
        choices=(("auto", _("Auto")),) + settings.LANGUAGES,
        default="auto",
        verbose_name=_("Language"),
    )
    timezone = models.CharField(
        max_length=50,
        choices=[("auto", _("Auto"))] + [(tz, tz) for tz in pytz.common_timezones],
        default="auto",
        verbose_name=_("Time Zone"),
    )

    def __str__(self):
        return f"{self.user.email}'s settings"
