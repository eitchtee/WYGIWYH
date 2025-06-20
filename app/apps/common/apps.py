from django.apps import AppConfig


class CommonConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.common"

    def ready(self):
        from django.contrib import admin
        from django.contrib.sites.models import Site
        from allauth.socialaccount.models import (
            SocialAccount,
            SocialApp,
            SocialToken,
        )

        admin.site.unregister(Site)
        admin.site.unregister(SocialAccount)
        admin.site.unregister(SocialApp)
        admin.site.unregister(SocialToken)
