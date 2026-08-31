from __future__ import annotations

from django.conf import settings

from apps.messaging.phone import InvalidPhoneNumber, normalize_to_e164
from apps.messaging.sms.base import FAILED, SmsResult
from apps.messaging.sms.registry import get_provider


def send_sms(*, to: str, body: str) -> SmsResult:
    """
    The one chokepoint every SMS send in the codebase goes through - mirrors
    apps.messaging.services.send_whatsapp_text and apps.common.mailer.send_email. A malformed
    or empty number is reported back as a FAILED SmsResult rather than raised, so a bad number
    behaves like any other delivery failure instead of a 500 or a broken transaction.
    """
    if not to:
        return SmsResult(status=FAILED, failure_reason="No recipient phone number.")
    try:
        normalized = normalize_to_e164(to)
    except InvalidPhoneNumber as exc:
        return SmsResult(status=FAILED, failure_reason=str(exc)[:255])
    return get_provider(settings.SMS_PROVIDER).send_text(to=normalized, body=body)
