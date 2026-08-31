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


def _row_is_clearly_a_drug(med: dict) -> bool:
    """A medication row that carries a name plus at least one other concrete prescribing
    detail. That combination is only ever produced by a read that actually worked - garbled
    OCR yields a bare name fragment and nothing else."""
    if not (med.get("name") or "").strip():
        return False
    if "[illegible]" in str(med.get("name", "")).lower():
        return False
    return any((med.get(key) or "") != "" for key in ("strength", "dose_pattern", "directions", "duration")) or med.get(
        "quantity"
    ) is not None


def extraction_confidence(fields: dict) -> float:
    """How much of a structured read to trust, 0-1: an equal blend of how cleanly the header
    parsed (prescriber / patient / date) and how well the medication rows came out. A clean
    script scores high on at least one side; a mangled handwriting scan scores low on both,
    which is the signal to withhold the read from the patient rather than show a page of
    guesses.

    The medication side takes the *better* of two views: how many rows linked to a real
    catalog SKU, and how many are clearly-parsed drug rows regardless of linkage. Catalog
    linkage alone was the original measure and it conflated two unrelated failures - "we
    couldn't read the page" and "we read it perfectly, but these drugs aren't stocked here".
    A foreign or out-of-catalog prescription (an Indian dental script: Augmentin, Enzoflam,
    Pan-D, Hexigel) scored 0 on a flawless read and was hidden from the patient. Parsed rows
    are discounted against linked ones - a linked row is stronger evidence - but they no
    longer score zero.

    An unmatched drug therefore does not sink the score, and neither does an unlabelled
    header. Both sides near zero is the case this is built to catch."""
    meds = fields.get("medications") or []
    header_hits = sum(1 for key in ("patient_name", "doctor_name", "prescription_date") if fields.get(key))
    header_score = header_hits / 3
    if not meds:
        # Header-only read (no drug lines survived): lean on the header alone, discounted.
        return round(0.6 * header_score, 2)
    link_score = sum(1 for med in meds if med.get("medicine_id")) / len(meds)
    parsed_score = sum(1 for med in meds if _row_is_clearly_a_drug(med)) / len(meds)
    med_score = max(link_score, 0.8 * parsed_score)
    return round(0.5 * med_score + 0.5 * header_score, 2)


def vision_confidence(fields: dict) -> float:
    """Confidence for a single-call vision read, which reports its own transcription quality
    instead of leaving it to be inferred from catalog linkage.

    The model's self-assessment is the base, scaled by how many medication rows it could read
    legibly: a read the model rates 0.9 with every row legible keeps 0.9; the same rating with
    half the rows marked illegible lands at ~0.56; with every row illegible it falls to ~0.23
    and is withheld. The legibility term has to be able to sink an otherwise-confident rating
    on its own - a model that says "0.9" while marking every drug unreadable has contradicted
    itself, and the rows are the part that matters.

    Catalog linkage deliberately plays no part here - whether a drug is stocked in Lebanon
    says nothing about whether the page was read correctly."""
    reported = fields.get("transcription_confidence")
    try:
        base = max(0.0, min(1.0, float(reported)))
    except (TypeError, ValueError):
        base = 0.0

    meds = fields.get("medications") or []
    if not meds:
        # Nothing prescribed was read. Whatever the model claims, this is a weak result - a
        # prescription with no drug lines is almost always a failed read, not an empty page -
        # and the discount has to be steep enough that a confident-sounding 1.0 still lands
        # below OCR_LOW_CONFIDENCE_THRESHOLD.
        return round(0.35 * base, 2)
    legible_ratio = sum(1 for med in meds if med.get("legible", True)) / len(meds)
    return round(base * (0.25 + 0.75 * legible_ratio), 2)


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


def structured_from_vision(raw: dict, provider: str) -> StructuredResult:
    """Turn a single-call vision read (apps.prescriptions.services.ocr.vision_structured)
    into the same ``StructuredResult`` the two-stage path produces, so every downstream
    reader - serializer, patient UI, pharmacy review form - sees one shape regardless of
    which pipeline ran.

    The vision shape carries a few fields the canonical one has no column for
    (``patient_age``, ``clinic_name``): they are folded into ``notes`` rather than dropped,
    since they are written on the page and a reviewing pharmacist should see them. Catalog
    reconciliation still runs - the model reads the name, this repo decides which SKU it is.
    """
    fields = reconcile_medications(_normalise(raw))

    context = " · ".join(
        part for part in (raw.get("clinic_name") or "", f"Age {raw['patient_age']}" if raw.get("patient_age") else "") if part
    )
    if context:
        fields["notes"] = f"{context}\n{fields['notes']}".strip() if fields["notes"] else context

    return StructuredResult(fields=fields, provider=provider, confidence=vision_confidence(raw))


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
        med["dose_pattern"] = str(med["dose_pattern"] or "").strip()
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
