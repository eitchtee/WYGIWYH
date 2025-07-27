from django.apps import AppConfig
from django.core.cache import cache


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

        # Delete the cache for update checks to prevent false-positives when the app is restarted
        # this will be recreated by the check_for_updates task
        cache.delete("update_check")
