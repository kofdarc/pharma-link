from __future__ import annotations

import json
import urllib.error
import urllib.request

from django.conf import settings

from apps.messaging.models import Message
from apps.messaging.providers.base import SendResult, WhatsAppProvider

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

    def _send(self, *, to: str, message: dict) -> SendResult:
        version = settings.WHATSAPP_GRAPH_API_VERSION
        if not version or not settings.WHATSAPP_PHONE_NUMBER_ID or not settings.WHATSAPP_ACCESS_TOKEN:
            return SendResult(
                status=Message.Status.FAILED,
                failure_reason="Meta WhatsApp provider is not fully configured.",
            )
        url = f"https://graph.facebook.com/{version}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
        payload = json.dumps({"messaging_product": "whatsapp", "to": to.lstrip("+"), **message}).encode("utf-8")
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

    def send_text(self, *, to: str, body: str) -> SendResult:
        return self._send(to=to, message={"type": "text", "text": {"body": body}})

    def send_template(
        self,
        *,
        to: str,
        template_name: str,
        language_code: str,
        body_parameters: list[str],
        button_url_suffix: str = "",
    ) -> SendResult:
        components = []
        if body_parameters:
            components.append(
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": str(value)} for value in body_parameters],
                }
            )
        if button_url_suffix:
            components.append(
                {
                    "type": "button",
                    "sub_type": "url",
                    "index": "0",
                    "parameters": [{"type": "text", "text": button_url_suffix}],
                }
            )
        template = {"name": template_name, "language": {"code": language_code}}
        if components:
            template["components"] = components
        return self._send(to=to, message={"type": "template", "template": template})
