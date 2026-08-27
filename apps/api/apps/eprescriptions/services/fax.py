from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass
class FaxResult:
    status: str
    provider_message_id: str = ""


class FaxProvider(ABC):
    """
    PrescribeIT's guaranteed-delivery model: if a prescription can't reach the patient
    digitally (no email on file, or the send failed), fax is the back-up channel. Mirrors
    apps.messaging.providers.base.WhatsAppProvider - a real fax gateway (e.g. an
    e-fax/Twilio-style API) plugs in as one more class here and a registry entry; call
    sites never change.
    """

    code: str

    @abstractmethod
    def send_fax(self, *, to: str, subject: str, text_body: str) -> FaxResult: ...


class ConsoleFaxProvider(FaxProvider):
    """Dev/test default (see settings.FAX_PROVIDER): logs instead of calling a real fax gateway."""

    code = "console"

    def send_fax(self, *, to: str, subject: str, text_body: str) -> FaxResult:
        logger.info("Fax[console] -> %s: %s\n%s", to, subject, text_body)
        return FaxResult(status="SENT", provider_message_id=f"console-fax-{uuid4().hex[:10]}")


_PROVIDERS: dict[str, FaxProvider] = {
    ConsoleFaxProvider.code: ConsoleFaxProvider(),
}


def get_provider(code: str) -> FaxProvider:
    try:
        return _PROVIDERS[code]
    except KeyError:
        raise ValueError(f"Unknown fax provider '{code}'.") from None
