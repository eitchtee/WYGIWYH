import os

from django.contrib.auth.hashers import check_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from oauth2_provider.models import get_application_model


Application = get_application_model()


def _get_env(name: str) -> str:
    return os.getenv(name, "").strip()


def _get_bool_env(name: str, default: bool = False) -> bool:
    raw = _get_env(name)
    if not raw:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


class Command(BaseCommand):
    help = (
        "Creates or updates the OAuth application used by MCP clients when "
        "MCP_OAUTH_CLIENT_* environment variables are configured."
    )

    def handle(self, *args, **options):
        client_id = _get_env("MCP_OAUTH_CLIENT_ID")
        client_secret = _get_env("MCP_OAUTH_CLIENT_SECRET")
        redirect_uris = " ".join(_get_env("MCP_OAUTH_REDIRECT_URIS").split())
        name = _get_env("MCP_OAUTH_CLIENT_NAME") or "WYGIWYH MCP"
        skip_authorization = _get_bool_env("MCP_OAUTH_SKIP_AUTHORIZATION", default=False)

        if not any([client_id, client_secret, redirect_uris]):
            self.stdout.write(
                self.style.NOTICE(
                    "MCP OAuth client env vars are not set. Skipping OAuth application setup."
                )
            )
            return

        missing = []
        if not client_id:
            missing.append("MCP_OAUTH_CLIENT_ID")
        if not client_secret:
            missing.append("MCP_OAUTH_CLIENT_SECRET")
        if not redirect_uris:
            missing.append("MCP_OAUTH_REDIRECT_URIS")
        if missing:
            raise CommandError(
                "Missing required MCP OAuth settings: " + ", ".join(missing)
            )

        application, created = Application.objects.get_or_create(
            client_id=client_id,
            defaults={
                "name": name,
                "client_type": Application.CLIENT_CONFIDENTIAL,
                "authorization_grant_type": Application.GRANT_AUTHORIZATION_CODE,
                "redirect_uris": redirect_uris,
                "skip_authorization": skip_authorization,
                "client_secret": client_secret,
                "hash_client_secret": True,
            },
        )

        updated_fields = []
        if application.name != name:
            application.name = name
            updated_fields.append("name")
        if application.client_type != Application.CLIENT_CONFIDENTIAL:
            application.client_type = Application.CLIENT_CONFIDENTIAL
            updated_fields.append("client_type")
        if (
            application.authorization_grant_type
            != Application.GRANT_AUTHORIZATION_CODE
        ):
            application.authorization_grant_type = Application.GRANT_AUTHORIZATION_CODE
            updated_fields.append("authorization_grant_type")
        if application.redirect_uris != redirect_uris:
            application.redirect_uris = redirect_uris
            updated_fields.append("redirect_uris")
        if application.skip_authorization != skip_authorization:
            application.skip_authorization = skip_authorization
            updated_fields.append("skip_authorization")
        if application.hash_client_secret is not True:
            application.hash_client_secret = True
            updated_fields.append("hash_client_secret")
        if not application.client_secret or not check_password(
            client_secret,
            application.client_secret,
        ):
            application.client_secret = client_secret
            updated_fields.append("client_secret")

        try:
            application.full_clean()
        except ValidationError as exc:
            errors = "; ".join(
                f"{field}: {', '.join(messages)}"
                for field, messages in exc.message_dict.items()
            )
            raise CommandError(f"Invalid MCP OAuth application settings: {errors}") from exc

        if created:
            application.save()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Created MCP OAuth application '{application.client_id}'."
                )
            )
            return

        if updated_fields:
            application.save(update_fields=updated_fields)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Updated MCP OAuth application '{application.client_id}'."
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"MCP OAuth application '{application.client_id}' is already up to date."
            )
        )
