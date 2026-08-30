from __future__ import annotations

from abc import ABC, abstractmethod

# The shape every extractor returns. Keys are always present; values default to
# "" / [] so a caller never has to guard for a missing key. `medications` is a
# list of {name, strength, quantity, directions, duration, refills}.
STRUCTURED_KEYS = ("patient_name", "patient_phone", "doctor_name", "prescription_date", "medications", "notes")
MEDICATION_KEYS = ("name", "strength", "quantity", "directions", "duration", "refills")


class NlpExtractorError(Exception):
    """A structured-extraction backend failed (network, auth, rate limit, unparseable response, ...)."""


class StructuredExtractor(ABC):
    """
    Turn the raw OCR transcription of a prescription (apps.prescriptions.services.ocr) into
    the structured fields a patient sees read-only and a pharmacist edits on review.

    Same plug-in shape as apps.prescriptions.services.ocr.base.OcrProvider and
    apps.analytics.providers.base.AssistantProvider: one class plus a registry entry, call
    sites (apps.prescriptions.services.structured) never change. The deterministic default
    (RegexExtractor) needs no configuration; OpenAiCompatibleExtractor is an opt-in upgrade
    behind settings.PRESCRIPTION_NLP_*.

    This is a *structuring* step, not an interpretation one - an extractor is only ever asked
    to lay out what the page already says into fields, never to add a dose, judge a
    prescription, or suggest a substitution (docs/PRD.md non-goals). Every value lands in an
    editable field a pharmacist confirms.
    """

    code: str

    @abstractmethod
    def extract(self, ocr_text: str) -> dict: ...
