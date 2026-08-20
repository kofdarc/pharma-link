"""
Keeps regulated medicine prices in sync with the Lebanese Ministry of Public Health's
published "Drugs Public Price List". MoPH re-publishes the entire list whenever the
reference exchange rate changes, so every regulated price moves together in one file -
this module is built around that: it always re-reads the latest published file and
brings the catalog in line with it, rather than tracking individual price deltas.

Safe to run as often as you like (e.g. daily via cron/systemd, the same way
`run_scheduler` is scheduled - see docs/DEPLOY_AWS.md): a pass that finds nothing
changed writes nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.request import Request, urlopen

import xlrd
from django.utils import timezone

from apps.medicines.models import Medicine, PriceRegime, ProductCategory

LIST_PAGE_URL = "https://moph.gov.lb/en/Pages/3/3101/drugs-public-price-list-"
USER_AGENT = "PharmaLink/1.0 (+contact: tech@mun.org.lb)"
REQUEST_TIMEOUT_SECONDS = 60

# Column indices in the MoPH "WebMarketed*.xls" export (0-indexed).
COL_BRAND = 2
COL_STRENGTH = 3
COL_FORM = 5
COL_MANUFACTURER = 7
COL_PUBLIC_PRICE_LL = 9
COL_DECISION_PRICE = 12  # USD-equivalent public price - what this app stores.

HOSPITAL_ONLY_FORM_KEYWORDS = [
    "infusion", "intravesical", "intratracheal", "intravenous", "intrathecal",
    "epidural", "dialysis", "hemodialysis", "peritoneal", "intracameral",
    "intravitreal", "irrigation solution",
]
SELF_ADMIN_EXCEPTIONS = [
    "pen", "prefilled", "pre-filled", "flexpen", "autoinjector", "auto-injector",
    "cartridge", "syringe",
]
HOSPITAL_ONLY_BARE_INJECTION = ["vial", "ampoule", "ampule", "injection", "injectable"]
HOSPITAL_MANUFACTURERS = {"serum products", "serum and solutions sal"}

FORM_MAP = {
    "tablet, film coated": "Tablet",
    "tablet": "Tablet",
    "tablet, scored": "Tablet",
    "tablet, coated": "Tablet",
    "tablet, sugar coated": "Tablet",
    "tablet, enteric coated": "Tablet",
    "tablet, gastroresistant": "Tablet",
    "tablet, chewable": "Chewable tablet",
    "tablet, orodispersible": "Orodispersible tablet",
    "tablet, prolonged release": "Extended release tablet",
    "tablet, extended release": "Extended release tablet",
    "capsule": "Capsule",
    "capsule, hard": "Capsule",
    "capsule, soft": "Softgel",
    "capsule, delayed release": "Capsule",
    "comprimés pelliculés": "Tablet",
    "comprimes pellicules": "Tablet",
    "comprimé pelliculé": "Tablet",
    "comprimés": "Tablet",
    "comprimé": "Tablet",
    "gélule": "Capsule",
    "gélules": "Capsule",
    "syrup": "Syrup",
    "oral solution": "Oral solution",
    "oral suspension": "Oral suspension",
    "suspension": "Suspension",
    "cream": "Cream",
    "ointment": "Ointment",
    "gel": "Gel",
    "suppository": "Suppository",
    "eye drops solution": "Eye drops",
    "eye drops": "Eye drops",
    "nasal spray suspension": "Nasal spray",
    "elixir": "Elixir",
    "caplet": "Caplet",
    "caplet, film coated": "Caplet",
    "fct": "Tablet",
    "inhalation powder": "Inhaler",
}

_MARKETED_FILE_RE = re.compile(
    r'href="(?P<href>/userfiles/files/HealthCareSystem/Pharmaceuticals/DrugsPublicPriceList/'
    r"(?P<folder_d>\d{1,2})-(?P<folder_m>\d{1,2})-(?P<folder_y>\d{4})/"
    r'WebMarketed(?P<base>\d{8})(?:-(?P<rev_d>\d{1,2})-(?P<rev_m>\d{1,2})-(?P<rev_y>\d{4}))?\.xls)"',
    re.IGNORECASE,
)


@dataclass
class MophRow:
    brand_name: str
    strength: str
    form: str
    manufacturer: str
    price_usd: Decimal


def _fetch(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return response.read()


def discover_latest_marketed_file_url() -> str:
    """Find the most recently published WebMarketed*.xls on the MoPH price list page."""
    html = _fetch(LIST_PAGE_URL).decode("utf-8", errors="ignore")
    best_href = None
    best_key = None
    for match in _MARKETED_FILE_RE.finditer(html):
        folder_date = (int(match["folder_y"]), int(match["folder_m"]), int(match["folder_d"]))
        if match["rev_y"]:
            revision_date = (int(match["rev_y"]), int(match["rev_m"]), int(match["rev_d"]))
        else:
            revision_date = folder_date
        key = max(folder_date, revision_date)
        if best_key is None or key > best_key:
            best_key = key
            best_href = match["href"]
    if not best_href:
        raise RuntimeError(f"Could not find a WebMarketed*.xls link on {LIST_PAGE_URL}")
    return "https://moph.gov.lb" + best_href


def _clean_form(raw: str) -> str:
    key = raw.strip().lower()
    return FORM_MAP.get(key, raw.strip()[:80])


def _title_case_brand(raw: str) -> str:
    return re.sub(r"\s+", " ", raw).strip().title()


def _is_hospital_only(form_lower: str, manufacturer_lower: str) -> bool:
    if manufacturer_lower in HOSPITAL_MANUFACTURERS:
        return True
    if any(k in form_lower for k in HOSPITAL_ONLY_FORM_KEYWORDS):
        return True
    if any(k in form_lower for k in HOSPITAL_ONLY_BARE_INJECTION):
        if not any(exc in form_lower for exc in SELF_ADMIN_EXCEPTIONS):
            return True
    return False


def parse_rows(xls_bytes: bytes) -> list[MophRow]:
    """Parse + filter the raw workbook into clean, deduplicated, retail-relevant rows."""
    book = xlrd.open_workbook(file_contents=xls_bytes)
    sheet = book.sheet_by_index(0)

    seen_keys = set()
    rows: list[MophRow] = []
    for r in range(1, sheet.nrows):
        brand_raw = str(sheet.cell_value(r, COL_BRAND)).strip()
        strength = str(sheet.cell_value(r, COL_STRENGTH)).strip()
        form_raw = str(sheet.cell_value(r, COL_FORM)).strip()
        manufacturer = str(sheet.cell_value(r, COL_MANUFACTURER)).strip()
        if not brand_raw or not form_raw:
            continue
        if _is_hospital_only(form_raw.lower(), manufacturer.lower()):
            continue

        try:
            price_usd = Decimal(str(round(float(sheet.cell_value(r, COL_DECISION_PRICE)), 2)))
        except (InvalidOperation, ValueError, TypeError):
            continue
        if price_usd <= 0:
            continue

        brand = _title_case_brand(brand_raw)
        form = _clean_form(form_raw)
        key = (brand.lower(), strength.lower(), form.lower())
        if key in seen_keys:
            continue
        seen_keys.add(key)

        rows.append(
            MophRow(
                brand_name=brand[:255],
                strength=strength[:80],
                form=form[:80],
                manufacturer=manufacturer[:160],
                price_usd=price_usd,
            )
        )
    return rows


def sync_prices(rows: list[MophRow], *, reference: str) -> dict:
    """Upsert Medicine records to match the given rows. Idempotent - unchanged rows are
    left untouched (and not written to the database at all)."""
    now = timezone.now()
    created = updated = unchanged = 0

    existing_by_key = {
        (m.brand_name.lower(), m.strength.lower(), m.form.lower()): m
        for m in Medicine.objects.filter(is_active=True)
    }

    for row in rows:
        key = (row.brand_name.lower(), row.strength.lower(), row.form.lower())
        medicine = existing_by_key.get(key)

        if medicine is None:
            Medicine.objects.create(
                brand_name=row.brand_name,
                generic_name="",
                strength=row.strength,
                form=row.form,
                manufacturer=row.manufacturer,
                category=ProductCategory.MEDICINE,
                price_regime=PriceRegime.REGULATED,
                regulated_price=row.price_usd,
                regulated_price_reference=reference,
                regulated_price_updated_at=now,
                requires_prescription=False,
                is_active=True,
            )
            created += 1
            continue

        needs_update = (
            medicine.price_regime != PriceRegime.REGULATED
            or medicine.regulated_price != row.price_usd
            or medicine.manufacturer != row.manufacturer
        )
        if needs_update:
            medicine.price_regime = PriceRegime.REGULATED
            medicine.regulated_price = row.price_usd
            medicine.regulated_price_reference = reference
            medicine.regulated_price_updated_at = now
            medicine.manufacturer = row.manufacturer
            medicine.category = ProductCategory.MEDICINE
            medicine.save(
                update_fields=[
                    "price_regime",
                    "regulated_price",
                    "regulated_price_reference",
                    "regulated_price_updated_at",
                    "manufacturer",
                    "category",
                    "updated_at",
                ]
            )
            updated += 1
        else:
            unchanged += 1

    return {
        "rows_processed": len(rows),
        "created": created,
        "updated": updated,
        "unchanged": unchanged,
    }


def run_sync(*, url: str | None = None, xls_bytes: bytes | None = None) -> dict:
    """Full pass: discover (unless a url/file is given), download, parse, sync."""
    if xls_bytes is None:
        url = url or discover_latest_marketed_file_url()
        xls_bytes = _fetch(url)
    rows = parse_rows(xls_bytes)
    reference = f"MoPH Drugs Public Price List ({url or 'local file'})"
    result = sync_prices(rows, reference=reference)
    result["source_url"] = url
    return result
