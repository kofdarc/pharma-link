from __future__ import annotations

import logging
from uuid import uuid4

from apps.messaging.sms.base import SENT, SmsProvider, SmsResult

logger = logging.getLogger(__name__)


class ConsoleSmsProvider(SmsProvider):
    """
    Dev/test default (see settings.SMS_PROVIDER): logs instead of calling AWS SNS, so the app
    can demo patient prescription texting end-to-end with no AWS account.
    """

    code = "console"

    def send_text(self, *, to: str, body: str) -> SmsResult:
        logger.info("SMS[console] -> %s: %s", to, body)
        return SmsResult(status=SENT, provider_message_id=f"console-sms-{uuid4().hex[:10]}")
