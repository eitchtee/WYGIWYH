from drf_spectacular.extensions import OpenApiAuthenticationExtension

from apps.users.models import APIToken


class APITokenAuthenticationScheme(OpenApiAuthenticationExtension):
    """Describes APITokenAuthentication in the API docs."""

    target_class = "apps.api.authentication.APITokenAuthentication"
    name = "apiToken"

    def get_security_definition(self, auto_schema):
        return {
            "type": "apiKey",
            "in": "header",
            "name": "Authorization",
            "description": (
                f"A personal API token, sent as `Token {APIToken.TOKEN_PREFIX}…`."
            ),
        }
