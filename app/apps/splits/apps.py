from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class SplitsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.splits"
    verbose_name = _("Split Expenses")
