"""
Pull the *header* fields off a prescription's OCR text - the prescriber's name and
the date it was written - so a patient photographing a paper prescription gets
those form fields filled in instead of re-typing a page they're already holding up
to the camera (see docs/AI_FEATURES.md §2).

The mirror image of apps.prescriptions.services.extraction, which reads the drug
lines and deliberately skips this metadata. The same boundary applies: everything
here is advisory. Each value lands in an editable field the patient confirms, and
a pharmacist reviews the scan by hand regardless (docs/PRD.md non-goals - no
diagnosis, no treatment advice).

Deterministic string parsing only, no model - identical in spirit to extraction.py.
Text mix on real Lebanese prescriptions is English + French + Arabic, so the
labels and month names cover all three.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from django.utils import timezone

# A prescription's own date is recent by definition (validity is measured in
# weeks - settings.PRESCRIPTION_VALIDITY_DAYS). A parsed date outside this window
# is almost always a misread or a date-of-birth that slipped past the label
# filter, so it's dropped rather than pre-filled.
_MAX_AGE_DAYS = 730
_MAX_FUTURE_DAYS = 3

# Month names: English + French, full and abbreviated (accented and not, since OCR
# frequently drops diacritics).
_MONTHS = {
    "jan": 1, "january": 1, "janv": 1, "janvier": 1,
    "feb": 2, "february": 2, "fev": 2, "fevr": 2, "févr": 2, "fevrier": 2, "février": 2,
    "mar": 3, "march": 3, "mars": 3,
    "apr": 4, "april": 4, "avr": 4, "avril": 4,
    "may": 5, "mai": 5,
    "jun": 6, "june": 6, "juin": 6,
    "jul": 7, "july": 7, "juil": 7, "juillet": 7,
    "aug": 8, "august": 8, "aout": 8, "août": 8,
    "sep": 9, "sept": 9, "september": 9, "septembre": 9,
    "oct": 10, "october": 10, "octobre": 10,
    "nov": 11, "november": 11, "novembre": 11,
    "dec": 12, "december": 12, "déc": 12, "decembre": 12, "décembre": 12,
}

# A label whose value IS the doctor - so "Doctor: Rima Khalil" and the bare title
# "Dr Rima Khalil" both resolve, but a stray word "doctor" in a sentence does not
# (the label form requires a ":" or "-" separator).
_DOCTOR_LABEL = re.compile(
    r"^\s*(?P<label>prescrib(?:er|ing\s+(?:doctor|physician))|prescribed\s+by|physician|"
    r"doctor|docteur|médecin|medecin|attending)\s*[:\-]\s*(?P<value>.+)$",
    re.IGNORECASE | re.UNICODE,
)
_DOCTOR_TITLE = re.compile(r"\b(?P<title>dre?|docteur)\.?\s+(?P<value>[^\n]+)", re.IGNORECASE | re.UNICODE)
_ARABIC_DOCTOR = re.compile(r"الطبيب\s*[:\-]?\s*(?P<value>[^\n]+)")

# Labels that mean this line's date is a doctor's title-label (so a leading "Dr."
# in the captured value should be folded into a single "Dr. " prefix).
_TITLE_LABELS = {"doctor", "docteur", "médecin", "medecin", "physician", "attending"}

_LEADING_TITLE = re.compile(r"^(?:dre?|docteur|prof(?:esseur)?|med|médecin)\.?\s+", re.IGNORECASE | re.UNICODE)
_ARABIC_LEADING_TITLE = re.compile(r"^د\.?\s*")
_CREDENTIAL_TAIL = re.compile(
    r"\b(?:m\.?d\.?|ph\.?d\.?|f\.?r\.?c\.?[a-z]*|licen[sc]e|lic|reg(?:istration)?|"
    r"clinic|clinique|hospital|h[oô]pital|phone|tel|mobile|fax|specialist|"
    r"consultant|spécialiste|specialiste)\b.*$",
    re.IGNORECASE | re.UNICODE,
)
_NOT_A_NAME = re.compile(r"\b(?:patient|name|nom|the)\b", re.IGNORECASE | re.UNICODE)
_HAS_ARABIC = re.compile(r"[؀-ۿ]")
_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)

# The patient's own name - a labelled line only ("Patient: ...", "Nom du patient: ...",
# "اسم المريض: ..."). Unlike the prescriber there's no bare-title form to fall back on, so a
# missing label just means "not found".
_PATIENT_LABEL = re.compile(
    r"^\s*(?:patient(?:\s*name)?|name\s*of\s*patient|nom(?:\s*(?:du|de)\s*patient|\s*complet)?|"
    r"pt\.?\s*name|اسم\s*المريض|المريض)\s*[:\-]\s*(?P<value>.+)$",
    re.IGNORECASE | re.UNICODE,
)
# A phone number on a line that calls itself one - "Tel: ...", "Phone ...", "هاتف: ...",
# "Mobile ...". Kept label-gated so a licence number or a date isn't picked up as a phone.
_PHONE_LABEL = re.compile(
    r"(?:t[ée]l(?:[ée]phone)?|phone|mobile|cell|gsm|portable|هاتف|جوال|موبايل)\s*(?:no\.?|number|#)?\s*[:\-]?\s*"
    r"(?P<value>[+()\d][()\d\s.\-]{5,20}\d)",
    re.IGNORECASE | re.UNICODE,
)
_PHONE_DIGITS = re.compile(r"[+()\d][()\d\s.\-]{5,20}\d")

_DOB_LINE = re.compile(
    r"birth|naissance|\bdob\b|\bd\.o\.b\b|ميلاد|expir|valable|valid\s+until|valid\s+through|renouvel",
    re.IGNORECASE | re.UNICODE,
)
_DATE_CONTEXT = re.compile(r"\bdate[dt]?\b|تاريخ|\bissued\b|\b[ée]mis\b|prescribed\s+on|rx\s*date|\ble\b", re.IGNORECASE | re.UNICODE)

_NUMERIC_DATE = re.compile(r"\b(\d{1,4})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*(\d{2,4})\b")
_DMY_TEXT = re.compile(r"\b(\d{1,2})\s+([^\W\d_]{3,})\.?\s+(\d{4})\b", re.UNICODE)
_MDY_TEXT = re.compile(r"\b([^\W\d_]{3,})\.?\s+(\d{1,2}),?\s+(\d{4})\b", re.UNICODE)


def extract_prescription_metadata(raw_text: str) -> dict:
    """The header fields read off a prescription: ``doctor_name``,
    ``prescription_date`` (ISO ``YYYY-MM-DD``), ``patient_name`` and
    ``patient_phone``. Keys are present only when a value was actually found - a
    caller should treat a missing key as "leave the field blank", never as an
    error."""
    text = raw_text or ""
    fields: dict[str, str] = {}

    doctor = extract_doctor_name(text)
    if doctor:
        fields["doctor_name"] = doctor

    rx_date = extract_prescription_date(text)
    if rx_date:
        fields["prescription_date"] = rx_date

    patient = extract_patient_name(text)
    if patient:
        fields["patient_name"] = patient

    phone = extract_patient_phone(text)
    if phone:
        fields["patient_phone"] = phone

    return fields


def extract_doctor_name(text: str) -> str | None:
    for line in (text or "").splitlines():
        label = _DOCTOR_LABEL.match(line)
        if label:
            cleaned = _clean_doctor_name(label.group("value"), had_title=label.group("label").lower() in _TITLE_LABELS)
            if cleaned:
                return cleaned

    for line in (text or "").splitlines():
        arabic = _ARABIC_DOCTOR.search(line)
        if arabic:
            cleaned = _clean_doctor_name(arabic.group("value"), had_title=True)
            if cleaned:
                return cleaned

        title = _DOCTOR_TITLE.search(line)
        if title:
            cleaned = _clean_doctor_name(title.group("value"), had_title=True)
            if cleaned:
                return cleaned

    return None


def _clean_doctor_name(value: str, *, had_title: bool) -> str | None:
    name = (value or "").strip()

    stripped = _LEADING_TITLE.sub("", name, count=1)
    if stripped != name:
        had_title = True
        name = stripped
    stripped = _ARABIC_LEADING_TITLE.sub("", name, count=1)
    if stripped != name:
        had_title = True
        name = stripped

    # Cut at the first digit or separator - drops trailing "License 4521",
    # "- Cardiology", "(Beirut)" etc. without a per-suffix list.
    name = re.split(r"[\d,;|/()\[\]{}\n\t]", name, maxsplit=1)[0]
    name = _CREDENTIAL_TAIL.sub("", name)
    name = re.sub(r"\s+", " ", name).strip(" .-–")

    if len(_LETTER.findall(name)) < 2 or len(name) > 60 or _NOT_A_NAME.search(name):
        return None

    if had_title and not _HAS_ARABIC.search(name) and not re.match(r"(?i)dr\b", name):
        name = f"Dr. {name}"
    return name


def extract_patient_name(text: str) -> str | None:
    for line in (text or "").splitlines():
        match = _PATIENT_LABEL.match(line)
        if not match:
            continue
        name = re.split(r"[\d,;|/()\[\]{}\n\t]", match.group("value"), maxsplit=1)[0]
        name = re.sub(r"\s+", " ", name).strip(" .:-–")
        if 2 <= len(_LETTER.findall(name)) and len(name) <= 60:
            return name
    return None


def extract_patient_phone(text: str) -> str | None:
    for line in (text or "").splitlines():
        if _DOB_LINE.search(line):
            continue
        match = _PHONE_LABEL.search(line)
        if match:
            cleaned = _clean_phone(match.group("value"))
            if cleaned:
                return cleaned
    return None


def _clean_phone(value: str) -> str | None:
    digits = re.sub(r"[^\d+]", "", value or "")
    core = digits[1:] if digits.startswith("+") else digits
    if 6 <= len(core) <= 15:
        return digits
    return None


def extract_prescription_date(text: str) -> str | None:
    labelled: date | None = None
    fallback: date | None = None

    for line in (text or "").splitlines():
        if _DOB_LINE.search(line):
            continue
        has_context = bool(_DATE_CONTEXT.search(line))
        for parsed in _iter_dates(line):
            if fallback is None:
                fallback = parsed
            if has_context and labelled is None:
                labelled = parsed

    chosen = labelled or fallback
    return chosen.isoformat() if chosen else None


def _iter_dates(line: str):
    for match in _NUMERIC_DATE.finditer(line):
        parsed = _from_numeric(*match.groups())
        if parsed:
            yield parsed
    for match in _DMY_TEXT.finditer(line):
        day, month_name, year = match.groups()
        parsed = _build_date(int(year), _MONTHS.get(month_name.lower()), int(day))
        if parsed:
            yield parsed
    for match in _MDY_TEXT.finditer(line):
        month_name, day, year = match.groups()
        parsed = _build_date(int(year), _MONTHS.get(month_name.lower()), int(day))
        if parsed:
            yield parsed


def _from_numeric(first: str, second: str, third: str) -> date | None:
    if len(first) == 4:  # 2026-03-14
        return _build_date(int(first), int(second), int(third))

    year = int(third)
    if year < 100:  # two-digit year: 24 -> 2024
        year += 2000

    a, b = int(first), int(second)
    if a > 12 and b <= 12:  # unambiguous day-first
        day, month = a, b
    elif b > 12 and a <= 12:  # unambiguous month-first (US-style)
        day, month = b, a
    else:  # ambiguous - Lebanon writes day-first
        day, month = a, b
    return _build_date(year, month, day)


def _build_date(year: int | None, month: int | None, day: int | None) -> date | None:
    if not month or not day:
        return None
    try:
        value = date(year, month, day)
    except ValueError:
        return None

    today = timezone.localdate()
    if value < today - timedelta(days=_MAX_AGE_DAYS) or value > today + timedelta(days=_MAX_FUTURE_DAYS):
        return None
    return value
