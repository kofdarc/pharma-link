from __future__ import annotations

import base64
import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

from apps.messaging.sms.base import FAILED, SENT, SmsProvider, SmsResult

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 10
_API_ROOT = "https://api.twilio.com/2010-04-01"


class TwilioSmsProvider(SmsProvider):
    """
    Real send via Twilio's REST API. Uses urllib (stdlib) rather than adding the twilio SDK,
    matching the outbound-HTTP precedent in apps.messaging.providers.meta_cloud. Chosen for
    markets where AWS SNS shared-route delivery fails (Lebanon among them) - Twilio has direct
    carrier coverage there.

    Needs TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_FROM (an SMS-capable Twilio number
    in E.164, or a Messaging Service SID beginning "MG"). All blank by default, so this adapter
    is only reachable once SMS_PROVIDER=twilio is set with real credentials.
    """

    code = "twilio"

    def send_text(self, *, to: str, body: str) -> SmsResult:
        sid = settings.TWILIO_ACCOUNT_SID
        token = settings.TWILIO_AUTH_TOKEN
        sender = settings.TWILIO_FROM
        if not sid or not token or not sender:
            return SmsResult(status=FAILED, failure_reason="Twilio SMS provider is not fully configured.")

        form = {"To": to, "Body": body}
        # A Messaging Service SID (MG...) goes in MessagingServiceSid; a plain number in From.
        form["MessagingServiceSid" if sender.startswith("MG") else "From"] = sender
        payload = urllib.parse.urlencode(form).encode("utf-8")

        request = urllib.request.Request(
            f"{_API_ROOT}/Accounts/{urllib.parse.quote(sid)}/Messages.json",
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": "Basic " + base64.b64encode(f"{sid}:{token}".encode()).decode(),
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            logger.warning("SMS[twilio] send to %s failed: HTTP %s %s", to, exc.code, detail)
            return SmsResult(status=FAILED, failure_reason=f"HTTP {exc.code}: {detail}"[:255])
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            logger.warning("SMS[twilio] send to %s failed: %s", to, exc)
            return SmsResult(status=FAILED, failure_reason=str(exc)[:255])

        # Twilio queues asynchronously: a 201 with status queued/accepted/sending/sent is a
        # successful hand-off. Only an explicit failed/undelivered here is a failure.
        if data.get("status") in {"failed", "undelivered"}:
            return SmsResult(
                status=FAILED,
                provider_message_id=data.get("sid", ""),
                failure_reason=str(data.get("error_message") or data.get("status"))[:255],
                raw=data,
            )
        return SmsResult(status=SENT, provider_message_id=data.get("sid", ""), raw=data)
