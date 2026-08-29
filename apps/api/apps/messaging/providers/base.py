from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class SendResult:
    status: str
    provider_message_id: str = ""
    raw: dict[str, Any] | None = None
    failure_reason: str = ""


class WhatsAppProvider(ABC):
    """
    The one method a real WhatsApp adapter needs: given a normalized E.164 number and a
    text body, send it and report back. Mirrors apps.payments.providers.base.PaymentProvider -
    a real gateway (Meta Cloud API today, whatever else later) plugs in as one more class
    here and a registry entry; call sites never change.
    """

    code: str

    @abstractmethod
    def send_text(self, *, to: str, body: str) -> SendResult: ...

    @abstractmethod
    def send_template(
        self,
        *,
        to: str,
        template_name: str,
        language_code: str,
        body_parameters: list[str],
        button_url_suffix: str = "",
    ) -> SendResult: ...
