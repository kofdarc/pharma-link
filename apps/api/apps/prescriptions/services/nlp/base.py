from __future__ import annotations

from abc import ABC, abstractmethod

# The shape every extractor returns. Keys are always present; values default to
# "" / [] so a caller never has to guard for a missing key. `medications` is a
# list of {name, strength, quantity, dose_pattern, directions, duration, refills}.
#
# `dose_pattern` holds dosing notation exactly as written on the page ("1-0-1", "1 cp x 3/j")
# while `directions` holds the plain reading of it ("1 tablet morning and night, after
# meals"). Two fields rather than one because the verbatim notation is the record of what the
# prescriber wrote and the expansion is a convenience - a pharmacist reviewing a row needs to
# see both, and a wrong expansion must never overwrite the original. Only the vision
# providers fill it in; the regex and text-NLP extractors leave it "".
STRUCTURED_KEYS = ("patient_name", "patient_phone", "doctor_name", "prescription_date", "medications", "notes")
MEDICATION_KEYS = ("name", "strength", "quantity", "dose_pattern", "directions", "duration", "refills")

# Added to every medication row by apps.prescriptions.services.structured after the extractor
# runs (and re-derived when a pharmacist edits `ocr_fields`): the catalog match for the
# `name` the extractor read. `medicine_id` is a Medicine PK string or "" when nothing
# matched; `catalog_name` is that row's display name; `match_confidence` is a 0-1 score.
# An extractor never fills these in itself - they are the platform's reconciliation, not the
# model's claim.
MEDICATION_CATALOG_KEYS = ("medicine_id", "catalog_name", "match_confidence")


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
