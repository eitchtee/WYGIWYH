import logging
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth import get_user_model

User = get_user_model()
logger = logging.getLogger(__name__)


class AutoConnectSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Custom adapter to automatically connect social accounts to existing users
    with the same email address.

    SECURITY WARNING:
    This adapter automatically connects OIDC accounts to existing local accounts
    based on email matching.

    If your OIDC provider allows unverified emails, this could lead to
    ACCOUNT TAKEOVER attacks where an attacker creates an OIDC account
    with someone else's email and gains access to their account.
    """

    def pre_social_login(self, request, sociallogin):
        """
        Invoked just after a user successfully authenticates via a
        social provider, but before the login is actually processed.

        If a user with the same email already exists, connect the social
        account to that existing user instead of creating a new account.
        """
        # If the social account is already connected to a user, do nothing
        if sociallogin.is_existing:
            return

        # Check if we have an email from the social provider
        if not sociallogin.email_addresses:
            logger.warning(
                "OIDC login attempted without email address. "
                f"Provider: {sociallogin.account.provider}"
            )
            return

        # Get the email from the social login
        email = sociallogin.email_addresses[0].email.lower()

        # Try to find an existing user with this email
        try:
            user = User.objects.get(email__iexact=email)

            # Log this connection for security audit trail
            logger.info(
                f"Auto-connecting OIDC account to existing user. "
                f"Email: {email}, Provider: {sociallogin.account.provider}, "
                f"User ID: {user.id}"
            )

            # Connect the social account to the existing user
            sociallogin.connect(request, user)

        except User.DoesNotExist:
            # No user with this email exists, proceed with normal signup flow
            logger.debug(
                f"No existing user found for email {email}. "
                "Proceeding with new account creation."
            )
            pass
        except User.MultipleObjectsReturned:
            # Multiple users with the same email (shouldn't happen with unique constraint)
            logger.error(
                f"Multiple users found with email {email}. "
                "This should not happen with unique constraint. "
                "Blocking auto-connect."
            )
            # Let the default behavior handle this
            pass
