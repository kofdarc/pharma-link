from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework.authentication import TokenAuthentication
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import AuthenticationFailed


def is_token_expired(token: Token) -> bool:
    return timezone.now() - token.created > timedelta(hours=settings.AUTH_TOKEN_TTL_HOURS)


class ExpiringTokenAuthentication(TokenAuthentication):
    """
    Plain DRF TokenAuthentication tokens never expire - a database leak or backup hands
    out permanently valid sessions with no way to force re-auth short of a bulk delete.
    Tokens now expire AUTH_TOKEN_TTL_HOURS after issue; an expired one is deleted on first
    use so it cannot be replayed. accounts.views.LoginView reissues a fresh token rather
    than reusing an expired one (DRF's authtoken is one-per-user, so login alone would
    otherwise keep handing back the same dead token forever).
    """

    def authenticate_credentials(self, key):
        user, token = super().authenticate_credentials(key)
        if is_token_expired(token):
            token.delete()
            raise AuthenticationFailed("Session expired. Log in again.")
        return user, token
