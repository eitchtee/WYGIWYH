from allauth.account.auth_backends import AuthenticationBackend


class SocialOnlyAuthenticationBackend(AuthenticationBackend):
    """Replaces the default backends when OIDC_DISABLE_LOCAL_LOGIN is on.

    Every e-mail and password is refused, wherever it's checked: the login
    page, the admin and the API's basic auth. OIDC logins still work, because
    allauth picks its own backend class, which this is, for those sessions.
    Permission checks keep working too, since they come from ModelBackend.
    """

    def authenticate(self, request, **credentials):
        return None
