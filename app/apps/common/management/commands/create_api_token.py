from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.users.models import APIToken


class Command(BaseCommand):
    help = "Creates a hashed API token for a WYGIWYH user and prints the raw token once."

    def add_arguments(self, parser):
        parser.add_argument("email", help="WYGIWYH user email that will own this token.")
        parser.add_argument(
            "--name",
            default="n8n",
            help="Human-readable token name. Defaults to 'n8n'.",
        )
        parser.add_argument(
            "--expires-in-days",
            type=int,
            default=None,
            help="Optional token lifetime in whole days.",
        )

    def handle(self, *args, **options):
        email = options["email"].strip()
        name = options["name"].strip()
        expires_in_days = options["expires_in_days"]

        if not email:
            raise CommandError("Email is required.")
        if not name:
            raise CommandError("Token name cannot be empty.")
        if expires_in_days is not None and expires_in_days <= 0:
            raise CommandError("--expires-in-days must be greater than zero.")

        user = get_user_model().objects.filter(email__iexact=email).first()
        if user is None:
            raise CommandError(f"No WYGIWYH user exists for '{email}'.")

        expires_at = None
        if expires_in_days is not None:
            expires_at = timezone.now() + timedelta(days=expires_in_days)

        token, raw_token = APIToken.objects.create_token(
            user=user,
            name=name,
            expires_at=expires_at,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Created API token '{token.name}' for {user.email} ({token.token_key})."
            )
        )
        self.stdout.write(raw_token)
