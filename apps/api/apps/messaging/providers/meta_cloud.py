from __future__ import annotations

import json
import urllib.error
import urllib.request

from django.conf import settings

from apps.messaging.models import Message
from apps.messaging.providers.base import SendResult, WhatsAppProvider

GRAPH_API_VERSION = "v20.0"
REQUEST_TIMEOUT_SECONDS = 10


class MetaCloudWhatsAppProvider(WhatsAppProvider):
    """
    Real send via the Meta WhatsApp Cloud API. Uses urllib (stdlib) rather than adding a
    `requests` dependency, matching the existing outbound-HTTP precedent in
    apps.integrations.services.webhooks. Needs WHATSAPP_ACCESS_TOKEN and
    WHATSAPP_PHONE_NUMBER_ID (see config/settings.py) - both blank by default, so this
    adapter is only reachable once WHATSAPP_PROVIDER is switched on with real credentials.
    """

    code = "meta_cloud"

    def send_text(self, *, to: str, body: str) -> SendResult:
        url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
        payload = json.dumps(
            {
                "messaging_product": "whatsapp",
                "to": to.lstrip("+"),
                "type": "text",
                "text": {"body": body},
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                data = json.loads(response.read().decode("utf-8"))
            message_id = (data.get("messages") or [{}])[0].get("id", "")
            return SendResult(status=Message.Status.SENT, provider_message_id=message_id, raw=data)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            return SendResult(status=Message.Status.FAILED, failure_reason=f"HTTP {exc.code}: {detail}"[:255])
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            return SendResult(status=Message.Status.FAILED, failure_reason=str(exc)[:255])
