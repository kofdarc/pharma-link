from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils.translation import gettext as _

from apps.common.mailer import send_email

logger = logging.getLogger(__name__)


def _uid_and_token(user) -> tuple[str, str]:
    return urlsafe_base64_encode(force_bytes(user.pk)), default_token_generator.make_token(user)


def send_password_reset_email(user) -> None:
    uid, token = _uid_and_token(user)
    reset_url = f"{settings.PUBLIC_WEB_BASE_URL}/reset-password/{uid}/{token}/"
    try:
        send_email(
            to=[user.email],
            subject=_("Reset your PharmaLink password"),
            text_body=_(
                "Hi,\n\nUse this link to set a new password: %(url)s\n\n"
                "If you didn't request this, you can ignore this email - your password hasn't changed.\n"
            )
            % {"url": reset_url},
        )
    except Exception:
        logger.exception("Failed to send password reset email to %s", user.email)


def send_verification_email(user) -> None:
    uid, token = _uid_and_token(user)
    verify_url = f"{settings.PUBLIC_WEB_BASE_URL}/verify-email/{uid}/{token}/"
    try:
        send_email(
            to=[user.email],
            subject=_("Verify your PharmaLink email"),
            text_body=_("Hi,\n\nConfirm your email to start ordering: %(url)s\n") % {"url": verify_url},
        )
    except Exception:
        logger.exception("Failed to send verification email to %s", user.email)
