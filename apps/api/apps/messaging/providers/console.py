import logging
from uuid import uuid4

from apps.messaging.models import Message
from apps.messaging.providers.base import SendResult, WhatsAppProvider

logger = logging.getLogger(__name__)


class ConsoleWhatsAppProvider(WhatsAppProvider):
    """
    Dev/test default (see settings.WHATSAPP_PROVIDER): logs instead of calling Meta's API, so
    the app needs no WhatsApp Business account to demo chat or reminders end-to-end.
    """

    code = "console"

    def send_text(self, *, to: str, body: str) -> SendResult:
        logger.info("WhatsApp[console] -> %s: %s", to, body)
        return SendResult(status=Message.Status.SENT, provider_message_id=f"console-{uuid4().hex[:10]}")

    def send_template(
        self,
        *,
        to: str,
        template_name: str,
        language_code: str,
        body_parameters: list[str],
        button_url_suffix: str = "",
    ) -> SendResult:
        logger.info(
            "WhatsApp[console] template=%s language=%s -> %s params=%s button=%s",
            template_name,
            language_code,
            to,
            body_parameters,
            button_url_suffix,
        )
        return SendResult(status=Message.Status.SENT, provider_message_id=f"console-{uuid4().hex[:10]}")
