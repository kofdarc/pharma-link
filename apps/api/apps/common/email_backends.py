from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)


class SESEmailBackend(BaseEmailBackend):
    """
    Sends mail through AWS SES v2 (`SendEmail` with a raw MIME payload) instead of SMTP.

    Raw MIME is used deliberately: it preserves the HTML alternative and the QR-code SVG
    attachment that apps.eprescriptions.services.mailer.send_prescription_email builds, which
    a templated SES send would drop. boto3 resolves credentials from the environment / task
    role exactly like the S3 storage config in config/settings.py - no SMTP secret to store.

    Enable with EMAIL_BACKEND="apps.common.email_backends.SESEmailBackend"; the sender
    identity in DEFAULT_FROM_EMAIL must be verified in SES (see docs/DEPLOY_AWS.md).
    """

    def __init__(self, *, fail_silently: bool = False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self._client = None

    def _get_client(self):
        if self._client is None:
            import boto3

            self._client = boto3.client("sesv2", region_name=settings.AWS_SES_REGION_NAME or None)
        return self._client

    def send_messages(self, email_messages) -> int:
        if not email_messages:
            return 0
        try:
            from botocore.exceptions import BotoCoreError, ClientError
        except ImportError:  # pragma: no cover - boto3/botocore is a declared dependency
            if not self.fail_silently:
                raise
            return 0

        try:
            client = self._get_client()
        except Exception:
            if not self.fail_silently:
                raise
            logger.exception("Could not build the SES client")
            return 0

        sent = 0
        for message in email_messages:
            recipients = message.recipients()
            if not recipients:
                continue
            mime = message.message()
            request = {
                "FromEmailAddress": message.from_email,
                "Destination": {
                    "ToAddresses": list(message.to),
                    "CcAddresses": list(message.cc),
                    "BccAddresses": list(message.bcc),
                },
                "Content": {"Raw": {"Data": mime.as_bytes(linesep="\r\n")}},
            }
            if settings.SES_CONFIGURATION_SET:
                request["ConfigurationSetName"] = settings.SES_CONFIGURATION_SET
            try:
                client.send_email(**request)
                sent += 1
            except (BotoCoreError, ClientError):
                logger.exception("SES send failed for message to %s", recipients)
                if not self.fail_silently:
                    raise
        return sent
