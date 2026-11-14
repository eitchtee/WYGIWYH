from django.apps import AppConfig


class ApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.api"

    def ready(self):
        import apps.api.schema  # noqa: F401  registers the API token scheme for the docs
