from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

# Plain-string statuses rather than an enum so this package needs no model import - mirrors
# the vocabulary apps.messaging.providers.base.SendResult already uses ("SENT" / "FAILED").
SENT = "SENT"
FAILED = "FAILED"


@dataclass
class SmsResult:
    status: str
    provider_message_id: str = ""
    raw: dict[str, Any] | None = None
    failure_reason: str = ""


class SmsProvider(ABC):
    """
    The one method a real SMS adapter needs: given an E.164 number and a text body, send it
    and report back. Mirrors apps.messaging.providers.base.WhatsAppProvider and
    apps.eprescriptions.services.fax.FaxProvider - a real gateway (AWS SNS today, whatever
    else later) plugs in as one more class here plus a registry entry; call sites never change.
    """

    code: str

    @abstractmethod
    def send_text(self, *, to: str, body: str) -> SmsResult: ...
