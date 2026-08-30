"""
One entry point - ``extract_structured(ocr_text)`` - that the upload flow and the pharmacy
review flow both call to turn a prescription's OCR transcription into the structured field
set the patient sees read-only and a pharmacist edits (docs/AI_FEATURES.md §2).

Runs the extractor named by ``settings.PRESCRIPTION_NLP_PROVIDER`` (``"regex"`` by default -
deterministic, offline, no account). If a configured model extractor raises or is
misconfigured, it falls back to the regex extractor rather than failing the upload: a patient
must never lose an upload because an optional gateway was down, and a pharmacist reviews the
result regardless.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.conf import settings

from apps.prescriptions.services.nlp.base import MEDICATION_KEYS, NlpExtractorError
from apps.prescriptions.services.nlp.regex_extractor import RegexExtractor
from apps.prescriptions.services.nlp.registry import get_extractor

logger = logging.getLogger(__name__)

_EMPTY = {
    "patient_name": "",
    "patient_phone": "",
    "doctor_name": "",
    "prescription_date": "",
    "medications": [],
    "notes": "",
}


@dataclass
class StructuredResult:
    fields: dict
    provider: str

    @property
    def is_empty(self) -> bool:
        return self.fields == _EMPTY


def extract_structured(ocr_text: str) -> StructuredResult:
    text = (ocr_text or "").strip()
    if not text:
        return StructuredResult(fields=dict(_EMPTY), provider="")

    configured = settings.PRESCRIPTION_NLP_PROVIDER or RegexExtractor.code
    if configured != RegexExtractor.code:
        try:
            extractor = get_extractor(configured)
            return StructuredResult(fields=_normalise(extractor.extract(text)), provider=configured)
        except (NlpExtractorError, ValueError):
            logger.warning("Prescription NLP extractor %r failed; falling back to regex", configured, exc_info=True)

    return StructuredResult(fields=_normalise(RegexExtractor().extract(text)), provider=RegexExtractor.code)


def _normalise(raw: dict) -> dict:
    """Guarantee the full key set and value types regardless of which extractor ran, so
    every downstream reader (serializer, patient UI, pharmacy form) can rely on the shape."""
    raw = raw or {}
    medications = []
    for entry in raw.get("medications") or []:
        if not isinstance(entry, dict):
            continue
        med = {key: entry.get(key, "") for key in MEDICATION_KEYS}
        med["name"] = str(med["name"] or "").strip()
        med["strength"] = str(med["strength"] or "").strip()
        med["directions"] = str(med["directions"] or "").strip()
        med["duration"] = str(med["duration"] or "").strip()
        med["quantity"] = med["quantity"] if isinstance(med["quantity"], int) else _int_or_none(med["quantity"])
        med["refills"] = med["refills"] if isinstance(med["refills"], int) else _int_or_none(med["refills"])
        if med["name"]:
            medications.append(med)

    return {
        "patient_name": str(raw.get("patient_name") or "").strip(),
        "patient_phone": str(raw.get("patient_phone") or "").strip(),
        "doctor_name": str(raw.get("doctor_name") or "").strip(),
        "prescription_date": str(raw.get("prescription_date") or "").strip(),
        "medications": medications,
        "notes": str(raw.get("notes") or "").strip(),
    }


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
