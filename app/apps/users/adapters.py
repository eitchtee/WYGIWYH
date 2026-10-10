import logging

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)


class AutoConnectSocialAccountAdapter(DefaultSocialAccountAdapter):
    """Link verified (or provider-trusted) emails case-insensitively.

    OIDC_TRUST_EMAIL=true makes allauth treat every provider email as verified.
    Only use that mode with an issuer that guarantees email ownership.
    """

    def pre_social_login(self, request, sociallogin):
        if sociallogin.is_existing:
            return

        for address in sociallogin.email_addresses:
            if not address.verified:
                continue
            try:
                user = get_user_model().objects.get(email__iexact=address.email)
            except get_user_model().DoesNotExist:
                continue
            except get_user_model().MultipleObjectsReturned:
                logger.error("Multiple local users match OIDC email; blocking auto-connect.")
                return

            sociallogin.connect(request, user)
            return
