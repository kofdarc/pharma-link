"""
One entry point - ``extract_structured(ocr_text)`` - that the upload flow and the pharmacy
review flow both call to turn a prescription's OCR transcription into the structured field
set the patient sees read-only and a pharmacist edits (docs/AI_FEATURES.md §2).

Runs the extractor named by ``settings.PRESCRIPTION_NLP_PROVIDER`` (``"regex"`` by default -
deterministic, offline, no account). If a configured model extractor raises or is
misconfigured, it falls back to the regex extractor rather than failing the upload: a patient
must never lose an upload because an optional gateway was down, and a pharmacist reviews the
result regardless.

Whichever extractor ran, every medication row is then reconciled against the medicine catalog
(``annotate_catalog_match``): the free-text ``name`` the extractor read is resolved to a real
``Medicine`` so the row carries a ``medicine_id`` a pharmacist can act on, not just a string.
The regex extractor matches internally too; doing it here as well means the model path gets
the same linkage, and a pharmacist's inline correction is re-matched on save (serializers).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.conf import settings

from apps.prescriptions.services.extraction import match_medicine
from apps.prescriptions.services.nlp.base import MEDICATION_CATALOG_KEYS, MEDICATION_KEYS, NlpExtractorError
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
    # 0-1 gauge of how much of this read to trust - see extraction_confidence(). 0.0 on the
    # empty result. Persisted to PrescriptionRecord.ocr_confidence and used to decide whether
    # the patient is shown the parsed read or a "a pharmacist will check your photo" notice.
    confidence: float = 0.0

    @property
    def is_empty(self) -> bool:
        return self.fields == _EMPTY


def extraction_confidence(fields: dict) -> float:
    """How much of a structured read to trust, 0-1: an equal blend of how cleanly the header
    parsed (prescriber / patient / date) and how many medication rows resolved to a real
    catalog SKU. A clean script scores high on at least one side; a mangled handwriting scan
    scores low on both, which is the signal to withhold the read from the patient rather than
    show a page of unlinked guesses.

    An unmatched drug does not by itself sink the score - the catalog is not exhaustive, and a
    fully parsed header is strong evidence the OCR worked. Both sides near zero is the case
    this is built to catch."""
    meds = fields.get("medications") or []
    header_hits = sum(1 for key in ("patient_name", "doctor_name", "prescription_date") if fields.get(key))
    header_score = header_hits / 3
    if not meds:
        # Header-only read (no drug lines survived): lean on the header alone, discounted.
        return round(0.6 * header_score, 2)
    link_score = sum(1 for med in meds if med.get("medicine_id")) / len(meds)
    return round(0.5 * link_score + 0.5 * header_score, 2)


def extract_structured(ocr_text: str) -> StructuredResult:
    text = (ocr_text or "").strip()
    if not text:
        return StructuredResult(fields=dict(_EMPTY), provider="")

    configured = settings.PRESCRIPTION_NLP_PROVIDER or RegexExtractor.code
    if configured != RegexExtractor.code:
        try:
            extractor = get_extractor(configured)
            fields = reconcile_medications(_normalise(extractor.extract(text)))
            return StructuredResult(fields=fields, provider=configured, confidence=extraction_confidence(fields))
        except (NlpExtractorError, ValueError):
            logger.warning("Prescription NLP extractor %r failed; falling back to regex", configured, exc_info=True)

    fields = reconcile_medications(_normalise(RegexExtractor().extract(text)))
    return StructuredResult(fields=fields, provider=RegexExtractor.code, confidence=extraction_confidence(fields))


def annotate_catalog_match(med: dict) -> dict:
    """Return a copy of one medication row with the catalog-match keys
    (:data:`MEDICATION_CATALOG_KEYS`) set from its ``name`` / ``strength``. Unmatched rows get
    ``medicine_id`` / ``catalog_name`` = "" and the best (sub-threshold) score, so a reviewer
    can still see how close it came."""
    medicine, confidence = match_medicine(med.get("name", ""), med.get("strength", "") or "")
    return {
        **med,
        "medicine_id": str(medicine.id) if medicine else "",
        "catalog_name": str(medicine) if medicine else "",
        "match_confidence": round(float(confidence or 0), 2),
    }


def reconcile_medications(fields: dict) -> dict:
    """Reconcile every medication row in a structured field set against the catalog. Safe to
    re-run (a pharmacist's edit passes back through here via the serializer)."""
    fields = dict(fields or {})
    fields["medications"] = [annotate_catalog_match(med) for med in fields.get("medications") or []]
    return fields


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
