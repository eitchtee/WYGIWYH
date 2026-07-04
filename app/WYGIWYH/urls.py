"""
URL configuration for WYGIWYH project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)
from allauth.socialaccount.providers.openid_connect.views import login, callback
from apps.common.decorators.demo import disabled_on_demo
from apps.common.oauth_views import (
    authorization_server_metadata,
    dynamic_client_registration,
)
from oauth2_provider import urls as _dot_urls


def _decorate_included(patterns, decorator):
    """Apply ``decorator`` to every view callback inside an included URLconf.

    django.urls does not support decorating ``include()`` directly, so we wrap
    each URLPattern's callback here. The OAuth2 endpoints issue credentials, so
    gate them behind the same DEMO-mode guard used elsewhere.
    """
    wrapped = []
    for pattern in patterns:
        pattern.callback = decorator(pattern.callback)
        wrapped.append(pattern)
    return wrapped


_oauth_patterns = _decorate_included(_dot_urls.urlpatterns, disabled_on_demo)


urlpatterns = [
    path("admin/", admin.site.urls),
    path("hijack/", include("hijack.urls")),
    path("__debug__/", include("debug_toolbar.urls")),
    path("__reload__/", include("django_browser_reload.urls")),
    path("", include("pwa.urls")),
    # path("api/", include("rest_framework.urls")),
    path("api/", include("apps.api.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path("auth/", include("allauth.urls")),  # allauth urls
    path(
        "oauth/",
        include((_oauth_patterns, _dot_urls.app_name), namespace="oauth2_provider"),
    ),
    path(
        ".well-known/oauth-authorization-server",
        disabled_on_demo(authorization_server_metadata),
        name="oauth-authorization-server-metadata",
    ),
    path(
        "oauth/register/",
        disabled_on_demo(dynamic_client_registration),
        name="oauth-dynamic-client-registration",
    ),
    # path("auth/oidc/<str:provider_id>/login/", login, name="openid_connect_login"),
    # path(
    #     "auth/oidc/<str:provider_id>/login/callback/",
    #     callback,
    #     name="openid_connect_callback",
    # ),
    path("", include("apps.transactions.urls")),
    path("", include("apps.common.urls")),
    path("", include("apps.users.urls")),
    path("", include("apps.accounts.urls")),
    path("", include("apps.net_worth.urls")),
    path("", include("apps.monthly_overview.urls")),
    path("", include("apps.yearly_overview.urls")),
    path("", include("apps.currencies.urls")),
    path("", include("apps.rules.urls")),
    path("", include("apps.calendar_view.urls")),
    path("", include("apps.dca.urls")),
    path("", include("apps.mini_tools.urls")),
    path("", include("apps.import_app.urls")),
    path("", include("apps.export_app.urls")),
    path("", include("apps.insights.urls")),
]
