from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class OcrResult:
    text: str
    provider: str
    # Mean word-level confidence (0-1) when the provider can report one (Tesseract), else
    # None. Not populated by AnthropicOcrProvider - a vision model doesn't expose an
    # equivalent per-word score the way a glyph-matching engine does.
    confidence: float | None = None


class OcrProviderError(Exception):
    """A provider's OCR call failed (network, auth, rate limit, malformed response, ...)."""


class UnsupportedFileType(Exception):
    """A provider can't read this file's format (e.g. a PDF against Tesseract)."""


class OcrProvider(ABC):
    """
    One method a prescription-image OCR adapter needs: read an already-opened file and return
    its transcribed text. Mirrors apps.messaging.providers.base.WhatsAppProvider and
    apps.payments.providers.base.PaymentProvider - a new backend plugs in as one class here
    plus a registry entry; call sites (apps.prescriptions.services.extraction) never change.

    Turning that text into candidate drug/dose/quantity lines is a separate, deterministic
    step (apps.prescriptions.services.extraction) that runs the same way regardless of which
    provider produced the text - this class's only job is pixels-to-text.
    """

    code: str

    @abstractmethod
    def extract_text(self, file, *, mime_type: str) -> OcrResult: ...
