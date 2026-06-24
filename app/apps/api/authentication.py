from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from apps.users.models import APIToken


class APITokenAuthentication(BaseAuthentication):
    keyword = "Token"

    def authenticate(self, request):
        auth = get_authorization_header(request).split()
        if not auth or auth[0].lower() != self.keyword.lower().encode():
            return None

        if len(auth) != 2:
            raise AuthenticationFailed("Invalid API token header.")

        try:
            raw_token = auth[1].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AuthenticationFailed("Invalid API token header.") from exc

        # Only claim tokens carrying our prefix; otherwise return None so the
        # request falls through to other authenticators (e.g. DRF's built-in
        # TokenAuthentication, which shares the "Token" keyword).
        if not raw_token.startswith(APIToken.TOKEN_PREFIX):
            return None

        try:
            token_key, token_secret = APIToken.parse_raw_token(raw_token)
        except ValueError as exc:
            raise AuthenticationFailed("Invalid API token.") from exc

        token = APIToken.objects.select_related("user").filter(token_key=token_key).first()
        if token is None or not token.check_secret(token_secret):
            raise AuthenticationFailed("Invalid API token.")
        if token.revoked_at is not None:
            raise AuthenticationFailed("API token has been revoked.")
        if token.is_expired():
            raise AuthenticationFailed("API token has expired.")
        if not token.user.is_active:
            raise AuthenticationFailed("User account is disabled.")

        self._touch_last_used(token)
        return (token.user, token)

    @staticmethod
    def _touch_last_used(token):
        # Avoid a write on every request: only refresh once per interval.
        now = timezone.now()
        interval = settings.API_TOKEN_LAST_USED_UPDATE_INTERVAL
        if (
            token.last_used_at is None
            or (now - token.last_used_at) >= timedelta(seconds=interval)
        ):
            token.last_used_at = now
            token.save(update_fields=["last_used_at"])

    def authenticate_header(self, request):
        return self.keyword
