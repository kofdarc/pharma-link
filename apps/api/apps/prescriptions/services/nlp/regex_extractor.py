"""
The deterministic default structured extractor - no model, no network, no configuration.

Assembles the same output shape OpenAiCompatibleExtractor produces from the two parsing
layers this app already has:

- apps.prescriptions.services.metadata - prescriber, date, patient name/phone
- apps.prescriptions.services.extraction - candidate drug lines matched to the catalog

plus a thin regex pass over each drug line for the directions ("how to take it"), duration
("how long to take it") and refill count the patient asked to see. Anything it can't find is
left blank for a pharmacist to fill in on review.
"""

from __future__ import annotations

import re

from apps.prescriptions.services.extraction import extract_candidate_lines
from apps.prescriptions.services.metadata import extract_prescription_metadata
from apps.prescriptions.services.nlp.base import StructuredExtractor

# "How to take it": a frequency/timing clause. English sig abbreviations (bid/tid/qid/qhs/
# prn/po), plain English ("twice daily", "every 8 hours", "at bedtime"), and the French
# posology shorthand common on Lebanese scripts ("1 cp x 3/j", "matin et soir", "avant les
# repas"). Matched loosely - the whole clause is kept, not parsed into a schedule.
_DIRECTIONS = re.compile(
    r"(?:"
    r"\b[btq]\.?i\.?d\.?\b|\bq\.?[dh]\.?s?\.?\b|\bq\d+h\b|\bp\.?r\.?n\.?\b|\bp\.?o\.?\b|\bstat\b|\bod\b|\bbd\b"
    r"|\b(?:once|twice|thrice|[1-6]\s*times?)\s*(?:a|per)?\s*(?:day|daily|week|d|j)\b"
    r"|\bevery\s+\d+\s*(?:h|hours?|days?)\b"
    r"|\d\s*(?:x|/)\s*(?:day|d|j|jour)\b|x\s*\d\s*/\s*j\b"
    r"|\b(?:before|after|with)\s+(?:meals?|food|breakfast|lunch|dinner)\b"
    r"|\bat\s+bedtime\b|\bon\s+an?\s+empty\s+stomach\b"
    r"|matin|soir|midi|avant\s+les?\s+repas|apr[eè]s\s+les?\s+repas|au\s+coucher|[àa]\s+je?un"
    r")"
    r"[^\n]*",
    re.IGNORECASE | re.UNICODE,
)
# "How long to take it".
_DURATION = re.compile(
    r"\b(?:for|during|pendant|x|during)\s*(\d{1,3})\s*(days?|day|weeks?|wk?s?|months?|mos?|jours?|j|semaines?|sem|mois)\b"
    r"|\b(\d{1,3})\s*(days?|weeks?|months?|jours?|semaines?|mois)\s*(?:course|supply|treatment|traitement)\b",
    re.IGNORECASE | re.UNICODE,
)
# Refills / repeats. "no refills" -> 0, "refill x2" / "2 refills" / "repeat 3" -> the number.
_REFILL_NUM = re.compile(r"(?:refill|repeat|renouvel\w*)\s*(?:x|:)?\s*(\d{1,2})|(\d{1,2})\s*refills?\b", re.IGNORECASE | re.UNICODE)
_REFILL_NONE = re.compile(r"\bno\s+(?:refill|repeat)s?\b|\b0\s*refills?\b|ne\s+pas\s+renouveler", re.IGNORECASE | re.UNICODE)

_DURATION_UNIT = {
    "day": "days", "days": "days", "jour": "days", "jours": "days", "j": "days",
    "week": "weeks", "weeks": "weeks", "wk": "weeks", "wks": "weeks", "semaine": "weeks", "semaines": "weeks", "sem": "weeks",
    "month": "months", "months": "months", "mo": "months", "mos": "months", "mois": "months",
}


class RegexExtractor(StructuredExtractor):
    code = "regex"

    def extract(self, ocr_text: str) -> dict:
        text = ocr_text or ""
        meta = extract_prescription_metadata(text)

        medications = []
        for candidate in extract_candidate_lines(text):
            line = candidate.get("raw_line", "")
            medications.append(
                {
                    "name": candidate.get("medicine_brand") or candidate.get("name_guess", ""),
                    "strength": candidate.get("dosage_guess", ""),
                    "quantity": candidate.get("quantity_guess"),
                    "directions": _directions(line),
                    "duration": _duration(line),
                    "refills": _refills(line),
                }
            )

        return {
            "patient_name": meta.get("patient_name", ""),
            "patient_phone": meta.get("patient_phone", ""),
            "doctor_name": meta.get("doctor_name", ""),
            "prescription_date": meta.get("prescription_date", ""),
            "medications": medications,
            "notes": "",
        }


def _directions(line: str) -> str:
    match = _DIRECTIONS.search(line or "")
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group(0)).strip(" .,-")[:120]


def _duration(line: str) -> str:
    match = _DURATION.search(line or "")
    if not match:
        return ""
    count = match.group(1) or match.group(3)
    unit = (match.group(2) or match.group(4) or "").lower()
    if not count:
        return ""
    return f"{int(count)} {_DURATION_UNIT.get(unit, unit)}".strip()


def _refills(line: str):
    if _REFILL_NONE.search(line or ""):
        return 0
    match = _REFILL_NUM.search(line or "")
    if match:
        return int(match.group(1) or match.group(2))
    return None
