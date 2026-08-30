"""
Turn raw OCR text (apps.prescriptions.services.ocr) into candidate drug lines: a name guess
matched against the catalog via the same fuzzy/alias matching search uses
(apps.medicines.services.search.best_catalog_match - see docs/AI_FEATURES.md §1), plus
whatever dosage/quantity tokens the line contained.

Deliberately advisory, not authoritative. Nothing here is persisted as a real order or
dispensed automatically - a pharmacist reviews and edits every line before it becomes a sale
(apps.sales.services.create_sale). See docs/PRD.md non-goals: no diagnosis, no treatment
advice, no automatic substitution.
"""

from __future__ import annotations

import re

from apps.medicines.models import Medicine
from apps.medicines.services.search import best_catalog_match

# Unit words after the quantity number - English plus the French posology units that show up
# on Lebanese prescriptions (cp/comprimé = tablet, gél/gélule = capsule, sachet).
QUANTITY_PATTERN = re.compile(
    r"(?:\bx\s*|\bqty[:\s]*|#)(\d{1,4})\b"
    r"|\b(\d{1,4})\s*(?:tabs?|tablets?|caps?|capsules?|units?|pcs?|cp|comprim[ée]s?|g[ée]l(?:ules?)?|sachets?)\b",
    re.IGNORECASE,
)
DOSAGE_PATTERN = re.compile(r"\b(\d+(?:\.\d+)?\s?(?:mg|mcg|g|ml|iu))\b", re.IGNORECASE)

# Lines that are prescription metadata, not a drug - skipped rather than sent through catalog
# matching, where they'd only ever fail to match anyway. English, French, and Arabic since
# that's the script mix on real Lebanese prescriptions (docs/AI_FEATURES.md §2).
METADATA_LINE_PREFIXES = (
    "patient",
    "doctor",
    "dr",
    "date",
    "signature",
    "clinic",
    "address",
    "phone",
    "age",
    "diagnosis",
    "rx no",
    "prescription no",
    # French (English "date"/"signature" above already cover the identical French spellings)
    "nom",
    "docteur",
    "clinique",
    "adresse",
    "téléphone",
    "tel",
    "âge",
    "diagnostic",
    "ordonnance",
    "cachet",
    # Arabic
    "اسم",  # patient/name
    "الطبيب",  # doctor
    "المريض",  # patient
    "التاريخ",  # date
    "العمر",  # age
    "العنوان",  # address
    "الهاتف",  # phone
    "التوقيع",  # signature
)
# \b after the prefix requires a non-word character (space, colon, period, end-of-string)
# to follow - plain startswith() would flag "Telfast 120mg" as metadata just because "tel"
# is a prefix of "telfast", which a real drug name easily collides with.
METADATA_LINE_PATTERN = re.compile(
    "^(?:" + "|".join(re.escape(prefix) for prefix in METADATA_LINE_PREFIXES) + r")\b", re.IGNORECASE | re.UNICODE
)
MIN_LINE_LENGTH = 3
# Clinic letterhead / footer boilerplate - a URL, an email, or a bare domain. Never a drug
# line, and on a scanned letterhead it's the noise most likely to survive OCR intact and get
# mistaken for a medication name.
BOILERPLATE_LINE_PATTERN = re.compile(r"https?://|www\.|\S+@\S+\.\S|\.(?:com|net|org|co|lb|gov)\b", re.IGNORECASE)


def _is_metadata_line(line: str) -> bool:
    lowered = line.strip().lower()
    if len(lowered) < MIN_LINE_LENGTH:
        return True
    if not any(char.isalpha() for char in lowered):
        return True
    if BOILERPLATE_LINE_PATTERN.search(lowered):
        return True
    return bool(METADATA_LINE_PATTERN.match(lowered))


def _normalize_strength(value: str) -> str:
    return re.sub(r"\s+", "", (value or "").lower())


def _prefer_strength_variant(medicine, dosage_guess: str):
    """
    best_catalog_match() matches on brand_name/generic_name/alias text only - it never looks
    at `strength`, so "Panadol 500mg" and "Panadol 1g" (two separate catalog rows sharing a
    brand) resolve to whichever one the name-fuzzy-match happens to rank first, ignoring the
    dose actually written on the line. If the OCR line carried a dosage and the matched row's
    strength doesn't agree with it, prefer an active sibling with the same brand_name whose
    strength does - a plain exact-match filter, not another fuzzy pass.
    """
    if not medicine or not dosage_guess:
        return medicine
    target = _normalize_strength(dosage_guess)
    if _normalize_strength(medicine.strength) == target:
        return medicine
    sibling = Medicine.objects.filter(is_active=True, brand_name__iexact=medicine.brand_name).exclude(id=medicine.id)
    for candidate in sibling:
        if _normalize_strength(candidate.strength) == target:
            return candidate
    return medicine


def match_medicine(name: str, strength: str = ""):
    """
    Resolve a free-text drug name (whatever OCR or a vision/LLM extractor read off the page)
    to a catalog ``Medicine``, using the same fuzzy/alias matching search uses plus the
    dose-aware sibling preference. Returns ``(medicine_or_none, confidence)`` where confidence
    is a 0-1 score; ``(None, score)`` when nothing clears the threshold.

    Shared by ``extract_candidate_lines`` (the regex pipeline) and
    ``apps.prescriptions.services.structured`` (every extractor's output), so a medication
    row lands linked to a real SKU no matter which extractor produced it - and so a
    pharmacist correcting the name on review gets it re-linked.
    """
    medicine, confidence = best_catalog_match(name or "")
    medicine = _prefer_strength_variant(medicine, strength)
    return medicine, confidence


def extract_candidate_lines(raw_text: str) -> list[dict]:
    candidates = []
    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line or _is_metadata_line(line):
            continue

        quantity = None
        quantity_match = QUANTITY_PATTERN.search(line)
        if quantity_match:
            quantity = int(quantity_match.group(1) or quantity_match.group(2))

        dosage_match = DOSAGE_PATTERN.search(line)
        dosage = dosage_match.group(1) if dosage_match else ""

        name_candidate = QUANTITY_PATTERN.sub(" ", line)
        name_candidate = DOSAGE_PATTERN.sub(" ", name_candidate)
        name_candidate = re.sub(r"[^\w]+", " ", name_candidate, flags=re.UNICODE).strip()
        if not name_candidate:
            continue

        medicine, confidence = match_medicine(name_candidate, dosage)
        if medicine is None and not dosage and quantity is None:
            # No catalog match, no dose, no quantity: nothing here says "drug". On a clean
            # printed script every real line clears this bar; on a mangled handwriting scan
            # this is what stops the clinic tagline, an address fragment or a garbled name
            # from being served to the patient as an invented medication.
            continue
        candidates.append(
            {
                "raw_line": line,
                "name_guess": name_candidate,
                "medicine_id": str(medicine.id) if medicine else None,
                "medicine_name": str(medicine) if medicine else "",
                # Bare brand, no strength/form - what a downstream re-match (or a pharmacist's
                # edit box) can resolve again cleanly, unlike the "Panadol 500mg Tablet" that
                # str(Medicine) produces.
                "medicine_brand": medicine.brand_name if medicine else "",
                "confidence": confidence,
                "quantity_guess": quantity,
                "dosage_guess": dosage,
            }
        )
    return candidates
