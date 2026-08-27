"""
Keeps the local medicine catalog in sync with the Lebanese Ministry of Public
Health's published drug data.

Three MoPH sources are combined, in this precedence order:

1. MOPH_ONLINE - the Lebanon National Drugs Database (moph.gov.lb/en/Drugs/...).
   Authoritative for MARKETED products and for the richer clinical fields (ATC,
   ingredients, route, B/G, subsidy) it alone publishes. See services/moph_online.py.
2. MOPH_MARKETED_EXCEL - the WebMarketed*.xls price list. No longer the primary
   source for marketed products (the online DB has richer data), but it is the
   *only* source of the USD "decision price" (`Medicine.regulated_price`) - the
   online DB only publishes a Lebanese-pound price, which is not the same figure
   and is kept in `moph_extra["price_ll"]` instead. It also doubles as a
   reconciliation check: if the online crawl and this file disagree sharply on
   which products exist, that's a sign the crawl missed pages.
3. MOPH_NON_MARKETED_EXCEL - the WebNonMarketed*.xls file. The only source for
   registered-but-not-currently-marketed products; sets `market_status`.

All three files/pages are keyed by MoPH's own "Code" field, which is populated,
unique, and stable across all three sources (verified against live MoPH data:
100% populated and unique within each Excel file, zero overlap between the two
Excel files, and the same value shown on the online detail page for a given
drug). `Medicine.moph_code` uses it as the canonical identity key - see
`sync_products()`. Brand/strength/form text is only used as a one-time fallback
match for medicine rows synced before `moph_code` existed.

Safe to run as often as you like: `sync_products` only writes fields that
actually changed, and a `market_status` transition only ever happens on positive
evidence from the relevant source - never inferred from a product's absence
elsewhere (a failed scrape or missed page must never mass-flip products to
NON_MARKETED, nor delete anything).
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from urllib.request import Request, urlopen

import xlrd
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.medicines.models import MarketStatus, Medicine, MophSource, PriceRegime, ProductCategory
from apps.medicines.services.search import normalize_name

logger = logging.getLogger(__name__)

LIST_PAGE_URL = "https://moph.gov.lb/en/Pages/3/3101/drugs-public-price-list-"
USER_AGENT = "PharmaLink/1.0 (+contact: tech@mun.org.lb)"
REQUEST_TIMEOUT_SECONDS = 60

# A full online crawl (see services/moph_online.py) reliably finds several thousand
# marketed products. If it finds far fewer, that's a broken scraper/pagination/HTML
# change, not a small MoPH update - abort rather than silently under-syncing.
MIN_EXPECTED_ONLINE_PRODUCTS = 1000

# Column indices in the MoPH "WebMarketed*.xls" export (0-indexed).
COL_CODE = 0
COL_BRAND = 2
COL_STRENGTH = 3
COL_FORM = 5
COL_MANUFACTURER = 7
COL_PUBLIC_PRICE_LL = 9
COL_DECISION_PRICE = 12  # USD-equivalent public price - what this app stores.

# Column indices in the MoPH "WebNonMarketed*.xls" export (0-indexed). This file has
# no price columns at all - MoPH does not set a regulated price for a drug that
# isn't being sold.
NM_COL_CODE = 0
NM_COL_REGISTRATION_NUMBER = 1
NM_COL_BRAND = 2
NM_COL_STRENGTH = 3
NM_COL_PRESENTATION = 4
NM_COL_FORM = 5
NM_COL_AGENT = 6
NM_COL_MANUFACTURER = 7
NM_COL_COUNTRY = 8
NM_COL_RESPONSIBLE_PARTY_NAME = 9
NM_COL_RESPONSIBLE_PARTY_COUNTRY = 10

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
_NON_MARKETED_FILE_RE = re.compile(
    r'href="(?P<href>/userfiles/files/HealthCareSystem/Pharmaceuticals/DrugsPublicPriceList/'
    r"(?P<folder_d>\d{1,2})-(?P<folder_m>\d{1,2})-(?P<folder_y>\d{4})/"
    r'WebNonMarketed(?P<base>\d{8})(?:-(?P<rev_d>\d{1,2})-(?P<rev_m>\d{1,2})-(?P<rev_y>\d{4}))?\.xls)"',
    re.IGNORECASE,
)

SOURCE_PRIORITY = {
    MophSource.MOPH_ONLINE: 0,
    MophSource.MOPH_MARKETED_EXCEL: 1,
    MophSource.MOPH_NON_MARKETED_EXCEL: 2,
}


@dataclass
class MophRow:
    """Legacy price-only row, kept as-is for `sync_prices`/`sync_moph_prices` and
    existing tests. New code should use `MophProductRow`."""

    brand_name: str
    strength: str
    form: str
    manufacturer: str
    price_usd: Decimal


@dataclass
class MophProductRow:
    """Superset row consumed by `sync_products`, the unified catalog upsert.

    `price_usd` is only ever populated by the Marketed Excel (see module
    docstring) - it is None for online-sourced and non-marketed rows.
    """

    brand_name: str
    strength: str
    form: str
    manufacturer: str
    market_status: str
    source: str
    source_reference: str
    moph_code: int | None = None
    price_usd: Decimal | None = None
    registration_number: str = ""
    classification: str = ""
    ingredients: str = ""
    route: str = ""
    extra: dict = field(default_factory=dict)


def _fetch(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return response.read()


def _discover_latest_file_url(pattern: re.Pattern, *, label: str) -> str:
    html = _fetch(LIST_PAGE_URL).decode("utf-8", errors="ignore")
    best_href = None
    best_key = None
    for match in pattern.finditer(html):
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
        raise RuntimeError(f"Could not find a {label} link on {LIST_PAGE_URL}")
    return "https://moph.gov.lb" + best_href


def discover_latest_marketed_file_url() -> str:
    """Find the most recently published WebMarketed*.xls on the MoPH price list page."""
    return _discover_latest_file_url(_MARKETED_FILE_RE, label="WebMarketed*.xls")


def discover_latest_non_marketed_file_url() -> str:
    """Find the most recently published WebNonMarketed*.xls on the MoPH price list page."""
    return _discover_latest_file_url(_NON_MARKETED_FILE_RE, label="WebNonMarketed*.xls")


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


def _non_empty(values: dict) -> dict:
    return {k: v for k, v in values.items() if v not in (None, "")}


def _parse_code(raw) -> int | None:
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return None


def parse_rows(xls_bytes: bytes, *, source_reference: str = "") -> list[MophProductRow]:
    """Parse + filter the raw WebMarketed workbook into clean, deduplicated,
    retail-relevant rows. Returns `MophProductRow`; `sync_prices` (legacy) only
    reads the subset of fields it needs, so this is safe for both call sites."""
    book = xlrd.open_workbook(file_contents=xls_bytes)
    sheet = book.sheet_by_index(0)

    seen_keys = set()
    rows: list[MophProductRow] = []
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
            MophProductRow(
                brand_name=brand[:255],
                strength=strength[:80],
                form=form[:80],
                manufacturer=manufacturer[:160],
                market_status=MarketStatus.MARKETED,
                source=MophSource.MOPH_MARKETED_EXCEL,
                source_reference=source_reference,
                moph_code=_parse_code(sheet.cell_value(r, COL_CODE)),
                price_usd=price_usd,
            )
        )
    return rows


def parse_non_marketed_rows(xls_bytes: bytes, *, source_reference: str = "") -> list[MophProductRow]:
    """Parse the WebNonMarketed workbook. No hospital-only filtering is applied
    here (unlike `parse_rows`): these products are registry metadata, not a
    sellable/orderable catalog, so there's no reason to exclude any form."""
    book = xlrd.open_workbook(file_contents=xls_bytes)
    sheet = book.sheet_by_index(0)

    seen_codes = set()
    rows: list[MophProductRow] = []
    for r in range(1, sheet.nrows):
        brand_raw = str(sheet.cell_value(r, NM_COL_BRAND)).strip()
        moph_code = _parse_code(sheet.cell_value(r, NM_COL_CODE))
        if not brand_raw or moph_code is None:
            continue
        if moph_code in seen_codes:
            continue
        seen_codes.add(moph_code)

        form_raw = str(sheet.cell_value(r, NM_COL_FORM)).strip()
        extra = _non_empty(
            {
                "presentation": str(sheet.cell_value(r, NM_COL_PRESENTATION)).strip(),
                "agent": str(sheet.cell_value(r, NM_COL_AGENT)).strip(),
                "country": str(sheet.cell_value(r, NM_COL_COUNTRY)).strip(),
                "responsible_party_name": str(sheet.cell_value(r, NM_COL_RESPONSIBLE_PARTY_NAME)).strip(),
                "responsible_party_country": str(sheet.cell_value(r, NM_COL_RESPONSIBLE_PARTY_COUNTRY)).strip(),
            }
        )

        rows.append(
            MophProductRow(
                brand_name=_title_case_brand(brand_raw)[:255],
                strength=str(sheet.cell_value(r, NM_COL_STRENGTH)).strip()[:80],
                form=(_clean_form(form_raw) if form_raw else "")[:80],
                manufacturer=str(sheet.cell_value(r, NM_COL_MANUFACTURER)).strip()[:160],
                market_status=MarketStatus.NON_MARKETED,
                source=MophSource.MOPH_NON_MARKETED_EXCEL,
                source_reference=source_reference,
                moph_code=moph_code,
                price_usd=None,
                registration_number=str(sheet.cell_value(r, NM_COL_REGISTRATION_NUMBER)).strip()[:80],
                extra=extra,
            )
        )
    return rows


def _merge_same_code_rows(rows_for_code: list[MophProductRow]) -> MophProductRow:
    """Multiple sources can report the same `moph_code` in one sync pass. The
    highest-priority source (online > marketed excel > non-marketed excel) wins
    for every field it actually supplies; a lower-priority source only fills in
    fields the winner left blank (this is how the Marketed Excel's USD price
    reaches a product that the online DB - which has no USD price at all -
    otherwise fully describes)."""
    ordered = sorted(rows_for_code, key=lambda r: SOURCE_PRIORITY[r.source])
    merged = replace(ordered[0])
    for row in ordered[1:]:
        for attr in ("registration_number", "classification", "ingredients", "route", "manufacturer", "brand_name", "strength", "form"):
            if not getattr(merged, attr) and getattr(row, attr):
                setattr(merged, attr, getattr(row, attr))
        if merged.price_usd is None and row.price_usd is not None:
            merged.price_usd = row.price_usd
        if row.extra:
            merged.extra = {**row.extra, **merged.extra}
    return merged


def sync_products(rows: list[MophProductRow]) -> dict:
    """Upsert `Medicine` rows from any combination of MoPH sources.

    Identity: matched by `moph_code` first. Rows without a `moph_code` match, and
    existing `Medicine`s that don't have one yet, fall back to the legacy
    brand/strength/form (and normalized brand+strength) match - a one-time bridge
    for the ~5.7k rows synced before this field existed. Once a `moph_code` is
    attached it is never reassigned.

    Field updates never let a blank/missing incoming value erase a good existing
    value (except the bookkeeping fields moph_source/moph_source_reference/
    moph_last_synced_at, and market_status - see below). `market_status` only
    moves to NON_MARKETED on a MOPH_NON_MARKETED_EXCEL row and only moves to
    MARKETED on a MOPH_ONLINE or MOPH_MARKETED_EXCEL row - never inferred from a
    product's mere absence from this batch.
    """
    now = timezone.now()

    invalid_rows = 0
    duplicates_skipped = 0
    by_code: dict[int, list[MophProductRow]] = defaultdict(list)
    rows_without_code: list[MophProductRow] = []
    for row in rows:
        if not row.brand_name or not row.form:
            invalid_rows += 1
            continue
        if row.moph_code is None:
            rows_without_code.append(row)
        else:
            by_code[row.moph_code].append(row)

    merged_rows: list[MophProductRow] = []
    for code, group in by_code.items():
        if len(group) > 1:
            duplicates_skipped += len(group) - 1
        merged_rows.append(_merge_same_code_rows(group))
    merged_rows.extend(rows_without_code)

    created = updated = unchanged = 0
    marketed = non_marketed = 0
    changed_to_non_marketed = changed_to_marketed = 0

    with transaction.atomic():
        existing_by_code = {m.moph_code: m for m in Medicine.objects.exclude(moph_code__isnull=True).select_for_update()}
        backfill_candidates = list(Medicine.objects.filter(is_active=True, moph_code__isnull=True).select_for_update())
        existing_by_key = {(m.brand_name.lower(), m.strength.lower(), m.form.lower()): m for m in backfill_candidates}
        existing_by_identity = defaultdict(list)
        for m in backfill_candidates:
            if m.category == ProductCategory.MEDICINE:
                existing_by_identity[(normalize_name(m.brand_name), normalize_name(m.strength))].append(m)

        for row in merged_rows:
            medicine = existing_by_code.get(row.moph_code) if row.moph_code is not None else None
            if medicine is None:
                key = (row.brand_name.lower(), row.strength.lower(), row.form.lower())
                medicine = existing_by_key.get(key)
                if medicine is None:
                    identity_matches = existing_by_identity.get((normalize_name(row.brand_name), normalize_name(row.strength)), [])
                    if len(identity_matches) == 1:
                        medicine = identity_matches[0]

            is_new = medicine is None
            if is_new:
                medicine = Medicine(is_active=True, category=ProductCategory.MEDICINE)

            changed = False

            def apply(attr: str, value):
                nonlocal changed
                if value not in (None, "") and getattr(medicine, attr) != value:
                    setattr(medicine, attr, value)
                    changed = True

            apply("moph_code", row.moph_code)
            apply("brand_name", row.brand_name)
            apply("strength", row.strength)
            apply("form", row.form)
            apply("manufacturer", row.manufacturer)
            apply("registration_number", row.registration_number)
            apply("classification", row.classification)
            apply("ingredients", row.ingredients)
            apply("route", row.route)

            if row.extra:
                merged_extra = {**medicine.moph_extra, **row.extra}
                if merged_extra != medicine.moph_extra:
                    medicine.moph_extra = merged_extra
                    changed = True

            if row.market_status == MarketStatus.NON_MARKETED:
                if medicine.price_regime != PriceRegime.FREE:
                    medicine.price_regime = PriceRegime.FREE
                    changed = True
            elif row.price_usd is not None:
                if medicine.regulated_price != row.price_usd:
                    medicine.regulated_price = row.price_usd
                    medicine.regulated_price_reference = row.source_reference
                    medicine.regulated_price_updated_at = now
                    changed = True
                if medicine.price_regime != PriceRegime.REGULATED:
                    medicine.price_regime = PriceRegime.REGULATED
                    changed = True
            elif is_new:
                # A brand-new MARKETED product with no USD price available in this
                # pass yet (online-only discovery, ahead of the next Marketed Excel
                # reconciliation). FREE keeps the active-regulated-price constraint
                # satisfiable; a later pass upgrades it once a price is known.
                medicine.price_regime = PriceRegime.FREE

            if row.market_status != medicine.market_status:
                medicine.market_status = row.market_status
                changed = True
                if row.market_status == MarketStatus.NON_MARKETED:
                    changed_to_non_marketed += 1
                else:
                    changed_to_marketed += 1

            medicine.moph_source = row.source
            medicine.moph_source_reference = row.source_reference
            medicine.moph_last_synced_at = now
            medicine.is_active = True

            try:
                with transaction.atomic():
                    medicine.save()
            except IntegrityError:
                logger.warning(
                    "Skipping MoPH code %s (%s %s %s): collides with an existing product's constraints.",
                    row.moph_code, row.brand_name, row.strength, row.form,
                )
                duplicates_skipped += 1
                continue

            if row.moph_code is not None:
                existing_by_code[row.moph_code] = medicine
            if is_new:
                created += 1
            elif changed:
                updated += 1
            else:
                unchanged += 1

            if medicine.market_status == MarketStatus.MARKETED:
                marketed += 1
            else:
                non_marketed += 1

    return {
        "rows_processed": len(rows),
        "created": created,
        "updated": updated,
        "unchanged": unchanged,
        "marketed": marketed,
        "non_marketed": non_marketed,
        "changed_marketed_to_non_marketed": changed_to_non_marketed,
        "changed_non_marketed_to_marketed": changed_to_marketed,
        "duplicates_skipped": duplicates_skipped,
        "invalid_rows": invalid_rows,
    }


def sync_prices(rows: list[MophRow], *, reference: str) -> dict:
    """Legacy price-only upsert used by `sync_moph_prices` for a fast regulated-
    price refresh. Superseded as the primary catalog pipeline by `sync_products`
    (see `run_full_sync`), but kept working unchanged so that command's existing
    schedule doesn't break."""
    now = timezone.now()
    created = updated = unchanged = 0

    existing_by_key = {
        (m.brand_name.lower(), m.strength.lower(), m.form.lower()): m
        for m in Medicine.objects.filter(is_active=True)
    }
    existing_by_identity = defaultdict(list)
    for existing in existing_by_key.values():
        if existing.category == ProductCategory.MEDICINE:
            existing_by_identity[(normalize_name(existing.brand_name), normalize_name(existing.strength))].append(existing)

    for row in rows:
        key = (row.brand_name.lower(), row.strength.lower(), row.form.lower())
        medicine = existing_by_key.get(key)
        if medicine is None:
            # The MoPH workbook changes dosage-form wording over time (for example
            # "Capsule, soft gelatin" vs "Softgel"). Reuse a unique product with
            # the same normalized brand + strength instead of creating a duplicate.
            identity_matches = existing_by_identity.get((normalize_name(row.brand_name), normalize_name(row.strength)), [])
            if len(identity_matches) == 1:
                medicine = identity_matches[0]

        if medicine is None:
            medicine = Medicine.objects.create(
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
            existing_by_key[key] = medicine
            existing_by_identity[(normalize_name(medicine.brand_name), normalize_name(medicine.strength))].append(medicine)
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
    """Legacy full pass used by `sync_moph_prices`: discover (unless a url/file is
    given), download, parse, sync prices only. See `run_full_sync` for the new
    online-DB-primary catalog pipeline."""
    if xls_bytes is None:
        url = url or discover_latest_marketed_file_url()
        xls_bytes = _fetch(url)
    rows = parse_rows(xls_bytes)
    reference = f"MoPH Drugs Public Price List ({url or 'local file'})"
    result = sync_prices(rows, reference=reference)
    result["source_url"] = url
    return result


def run_full_sync(
    *,
    letters: list[str] | None = None,
    max_pages_per_letter: int | None = None,
    delay_seconds: float = 0.3,
    non_marketed_xls_bytes: bytes | None = None,
    non_marketed_url: str | None = None,
    marketed_xls_bytes: bytes | None = None,
    marketed_url: str | None = None,
    skip_marketed_excel_check: bool = False,
    skip_non_marketed_excel: bool = False,
) -> dict:
    """The full catalog sync: online DB (marketed) + Non-Marketed Excel, with the
    Marketed Excel used only for its USD price and as a reconciliation check
    (see module docstring). Implements the flow: crawl -> validate -> parse Excel
    files -> upsert everything in one transaction -> log a summary.

    `letters`/`max_pages_per_letter` only scope the online crawl - the Excel files
    have no equivalent "scope" (they're single downloads, not paginated), so a dev
    smoke test that only wants to exercise the online crawl MUST also pass
    `skip_non_marketed_excel=True` (and/or `skip_marketed_excel_check=True`),
    otherwise it will still run a full production-sized Excel sync.
    """
    from apps.medicines.services import moph_online

    online_rows, crawl_stats = moph_online.crawl_marketed_online(
        delay_seconds=delay_seconds,
        letters=letters or moph_online.LETTERS,
        max_pages_per_letter=max_pages_per_letter,
    )

    is_full_crawl = letters is None and max_pages_per_letter is None
    if is_full_crawl and len(online_rows) < MIN_EXPECTED_ONLINE_PRODUCTS:
        logger.error(
            "MoPH online crawl returned only %d products (expected at least %d) - "
            "aborting catalog sync without writing anything. Incomplete-pagination letters: %s",
            len(online_rows), MIN_EXPECTED_ONLINE_PRODUCTS, crawl_stats.letters_with_incomplete_pagination,
        )
        return {
            "aborted": True,
            "reason": "online_crawl_too_small",
            "online_products_found": len(online_rows),
            "crawl_stats": vars(crawl_stats),
        }

    if crawl_stats.letters_with_incomplete_pagination:
        logger.warning("MoPH online crawl had incomplete pagination for letters: %s", crawl_stats.letters_with_incomplete_pagination)
    if crawl_stats.detail_fetch_failures:
        logger.warning("MoPH online crawl failed to fetch %d product detail pages.", crawl_stats.detail_fetch_failures)

    non_marketed_rows: list[MophProductRow] = []
    if not skip_non_marketed_excel:
        if non_marketed_xls_bytes is None:
            non_marketed_url = non_marketed_url or discover_latest_non_marketed_file_url()
            non_marketed_xls_bytes = _fetch(non_marketed_url)
        non_marketed_reference = f"MoPH Non Marketed Drugs Public Price List ({non_marketed_url or 'local file'})"
        non_marketed_rows = parse_non_marketed_rows(non_marketed_xls_bytes, source_reference=non_marketed_reference)

    all_rows = list(online_rows) + list(non_marketed_rows)
    marketed_excel_stats = {}

    if not skip_marketed_excel_check:
        try:
            if marketed_xls_bytes is None:
                marketed_url = marketed_url or discover_latest_marketed_file_url()
                marketed_xls_bytes = _fetch(marketed_url)
            marketed_reference = f"MoPH Drugs Public Price List ({marketed_url or 'local file'})"
            marketed_rows = parse_rows(marketed_xls_bytes, source_reference=marketed_reference)
            all_rows += marketed_rows

            online_codes = {r.moph_code for r in online_rows if r.moph_code is not None}
            marketed_excel_codes = {r.moph_code for r in marketed_rows if r.moph_code is not None}
            missed_by_online = marketed_excel_codes - online_codes
            marketed_excel_stats = {
                "marketed_excel_rows": len(marketed_rows),
                "codes_in_excel_missed_by_online_crawl": len(missed_by_online),
            }
            if marketed_excel_codes and len(missed_by_online) > 0.1 * len(marketed_excel_codes):
                logger.warning(
                    "Online crawl is missing %d/%d products (%.1f%%) that are present in the Marketed Excel - possible scraper gap.",
                    len(missed_by_online), len(marketed_excel_codes),
                    100 * len(missed_by_online) / len(marketed_excel_codes),
                )
        except Exception:
            logger.exception("Marketed Excel reconciliation pass failed; continuing with online + non-marketed data only.")

    result = sync_products(all_rows)
    result["crawl_stats"] = vars(crawl_stats)
    result.update(marketed_excel_stats)

    logger.info(
        "MoPH sync completed\n\n"
        "Online marketed fetched: %d\nNon-marketed Excel rows: %d\n\n"
        "Created: %d\nUpdated: %d\nUnchanged: %d\n\n"
        "Marketed: %d\nNon-marketed: %d\n\n"
        "Changed MARKETED -> NON_MARKETED: %d\nChanged NON_MARKETED -> MARKETED: %d\n\n"
        "Duplicates skipped/resolved: %d\nInvalid rows: %d",
        len(online_rows), len(non_marketed_rows),
        result["created"], result["updated"], result["unchanged"],
        result["marketed"], result["non_marketed"],
        result["changed_marketed_to_non_marketed"], result["changed_non_marketed_to_marketed"],
        result["duplicates_skipped"], result["invalid_rows"],
    )
    return result
