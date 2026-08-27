"""
Scrapes the MoPH "Lebanon National Drugs Database"
(https://www.moph.gov.lb/en/Drugs/index/3/4848/lebanon-national-drugs-database),
the authoritative online source for currently MARKETED products - see the module
docstring in services/moph_sync.py for how this fits into the overall catalog sync.

The site (a CakePHP app) has no bulk export or API. Getting a product's full field
set - crucially `code`, the identity key `moph_sync.sync_products` matches on -
requires two HTTP round trips per product:

1. A listing page per starting letter (A-Z), paginated ~30 rows/page, giving only
   ATC/Name/B-G/Ingredients/Dosage/Form/Price plus a link to:
2. The product's detail page, which has the full 20-field table (ATC, B/G,
   Ingredients, code, Registration Nb, Name, Dosage, Presentation, Form, Route,
   Agent, Laboratory, Country, Price, Pharmacist Margin, Stratum, Responsible
   Party Name, Responsible Party Country, Exch_date, %SUBSIDY).

A full crawl is on the order of 5,000-8,000 requests; `delay_seconds` paces it to
avoid hammering a government site. `page_fetcher`/`detail_fetcher` are injectable
so `crawl_marketed_online` is testable without any network access.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from urllib.request import Request, urlopen

from apps.medicines.models import MarketStatus, MophSource
from apps.medicines.services.moph_sync import MophProductRow, USER_AGENT, _clean_form, _title_case_brand

LETTERS = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
BASE_URL = "https://www.moph.gov.lb"
LISTING_PATH = "/en/Drugs/index/3/4848/letter:{letter}/page:{page}/sort:Drug.brand_name/direction:ASC"
DETAIL_PATH = "/en/Drugs/view/{view_id}"
REQUEST_TIMEOUT_SECONDS = 60

_DETAIL_FIELD_ORDER = [
    "atc", "b_g", "ingredients", "code", "registration_number", "brand_name",
    "strength", "presentation", "form", "route", "agent", "laboratory", "country",
    "price_text", "pharmacist_margin", "stratum", "responsible_party_name",
    "responsible_party_country", "exch_date", "subsidy_percent",
]


@dataclass
class OnlineListingRow:
    view_id: int
    atc: str
    brand_name: str
    b_g: str
    ingredients: str
    strength: str
    form: str
    price_text: str


@dataclass
class CrawlStats:
    letters_attempted: int = 0
    pages_fetched: int = 0
    pages_expected: int = 0
    listing_rows_found: int = 0
    unique_codes_found: int = 0
    detail_fetch_failures: int = 0
    letters_with_incomplete_pagination: list[str] = field(default_factory=list)


def _http_get(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return response.read().decode("utf-8", errors="ignore")


def fetch_listing_page(letter: str, page: int) -> str:
    return _http_get(BASE_URL + LISTING_PATH.format(letter=letter, page=page))


def fetch_detail_page(view_id: int) -> str:
    return _http_get(BASE_URL + DETAIL_PATH.format(view_id=view_id))


def _clean_cell_text(raw: str) -> str:
    text = re.sub(r"<!--.*?-->", "", raw, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _parse_last_page(html: str) -> int:
    page_numbers = [int(n) for n in re.findall(r"page:(\d+)", html)]
    return max(page_numbers) if page_numbers else 1


def parse_listing_page(html: str) -> tuple[list[OnlineListingRow], int]:
    """Returns (rows on this page, last page number for this letter)."""
    rows: list[OnlineListingRow] = []
    body_match = re.search(r"<tbody>(.*?)</tbody>", html, re.S)
    if body_match:
        for row_match in re.finditer(r"<tr>\s*(.*?)\s*</tr>", body_match.group(1), re.S):
            cells = re.findall(r'<a[^>]*href="(/en/Drugs/view/(\d+))"[^>]*>(.*?)</a>', row_match.group(1), re.S)
            if len(cells) < 7:
                continue
            view_id = int(cells[0][1])
            values = [_clean_cell_text(c[2]) for c in cells[:7]]
            atc, brand_name, b_g, ingredients, strength, form, price_text = values
            rows.append(OnlineListingRow(view_id, atc, brand_name, b_g, ingredients, strength, form, price_text))
    return rows, _parse_last_page(html)


def parse_detail_page(html: str) -> dict[str, str] | None:
    table_match = re.search(r'<table class="table">\s*<thead>.*?</thead>\s*<tbody>\s*<tr>(.*?)</tr>', html, re.S)
    if not table_match:
        return None
    # The live markup has HTML-commented-out placeholder <td></td>s (leftover from a
    # since-removed column) - strip comments first or they'd be matched as real cells
    # and shift every field that follows.
    row_html = re.sub(r"<!--.*?-->", "", table_match.group(1), flags=re.S)
    cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.S)
    if len(cells) < len(_DETAIL_FIELD_ORDER):
        return None
    values = [_clean_cell_text(c) for c in cells[: len(_DETAIL_FIELD_ORDER)]]
    return dict(zip(_DETAIL_FIELD_ORDER, values))


def _parse_ll_price(text: str) -> Decimal | None:
    cleaned = text.replace(",", "").replace("L.L", "").strip()
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _non_empty(values: dict) -> dict:
    return {k: v for k, v in values.items() if v not in (None, "")}


def build_online_row(detail: dict[str, str], *, source_reference: str) -> MophProductRow | None:
    """Pure transform from a parsed detail-page dict to a `MophProductRow`.
    Returns None for a detail page missing the two things that make a row usable:
    `code` (the identity key) and a brand name."""
    try:
        moph_code = int(float(detail.get("code", "")))
    except (ValueError, TypeError):
        return None
    brand_raw = detail.get("brand_name", "").strip()
    if not brand_raw:
        return None

    form_raw = detail.get("form", "").strip()
    ll_price = _parse_ll_price(detail.get("price_text", ""))
    extra = _non_empty(
        {
            "presentation": detail.get("presentation", ""),
            "agent": detail.get("agent", ""),
            "laboratory": detail.get("laboratory", ""),
            "country": detail.get("country", ""),
            "pharmacist_margin": detail.get("pharmacist_margin", ""),
            "stratum": detail.get("stratum", ""),
            "responsible_party_name": detail.get("responsible_party_name", ""),
            "responsible_party_country": detail.get("responsible_party_country", ""),
            "exch_date": detail.get("exch_date", ""),
            "subsidy_percent": detail.get("subsidy_percent", ""),
            "brand_generic": detail.get("b_g", ""),
            "price_ll": str(ll_price) if ll_price is not None else "",
        }
    )

    return MophProductRow(
        brand_name=_title_case_brand(brand_raw)[:255],
        strength=detail.get("strength", "").strip()[:80],
        form=(_clean_form(form_raw) if form_raw else "")[:80],
        manufacturer=detail.get("laboratory", "").strip()[:160],
        market_status=MarketStatus.MARKETED,
        source=MophSource.MOPH_ONLINE,
        source_reference=source_reference,
        moph_code=moph_code,
        price_usd=None,
        registration_number=detail.get("registration_number", "").strip()[:80],
        classification=detail.get("atc", "").strip()[:120],
        ingredients=detail.get("ingredients", "").strip(),
        route=detail.get("route", "").strip()[:80],
        extra=extra,
    )


def crawl_marketed_online(
    *,
    letters: list[str] | None = None,
    max_pages_per_letter: int | None = None,
    delay_seconds: float = 0.3,
    page_fetcher=fetch_listing_page,
    detail_fetcher=fetch_detail_page,
) -> tuple[list[MophProductRow], CrawlStats]:
    stats = CrawlStats()
    listing_rows_by_id: dict[int, OnlineListingRow] = {}

    for letter in letters or LETTERS:
        stats.letters_attempted += 1
        page = 1
        last_page = 1
        incomplete = False
        while True:
            try:
                html = page_fetcher(letter, page)
            except Exception:
                # A network/HTTP failure partway through a letter must not abort the
                # whole A-Z crawl - record it and move on to the next letter. Since
                # market_status only ever moves to NON_MARKETED on positive evidence
                # from the Non-Marketed Excel (never from a missing online row),
                # this can't cause a product to be wrongly demoted - it can only
                # cause a real MARKETED promotion/enrichment to be missed this pass.
                incomplete = True
                break
            page_rows, page_last_page = parse_listing_page(html)
            stats.pages_fetched += 1
            if page == 1:
                last_page = page_last_page
                stats.pages_expected += last_page
                if not page_rows:
                    break
            for row in page_rows:
                listing_rows_by_id[row.view_id] = row
            stats.listing_rows_found += len(page_rows)

            if max_pages_per_letter and page >= max_pages_per_letter:
                break
            if page >= last_page:
                break
            page += 1
            if delay_seconds:
                time.sleep(delay_seconds)

        if incomplete:
            stats.letters_with_incomplete_pagination.append(letter)
        if delay_seconds:
            time.sleep(delay_seconds)

    source_reference = "MoPH Lebanon National Drugs Database (online)"
    product_rows: list[MophProductRow] = []
    for view_id in listing_rows_by_id:
        try:
            detail_html = detail_fetcher(view_id)
            detail = parse_detail_page(detail_html)
        except Exception:
            detail = None
        if detail is None:
            stats.detail_fetch_failures += 1
            continue
        row = build_online_row(detail, source_reference=source_reference)
        if row is not None:
            product_rows.append(row)
        else:
            stats.detail_fetch_failures += 1
        if delay_seconds:
            time.sleep(delay_seconds)

    stats.unique_codes_found = len({r.moph_code for r in product_rows if r.moph_code is not None})
    return product_rows, stats
