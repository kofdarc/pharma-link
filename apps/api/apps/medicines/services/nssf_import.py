"""
Parse the NSSF (National Social Security Fund / CNSS) reimbursable-drug lists and apply
their coverage to the Medicine catalog.

The NSSF publishes coverage as two PDF lists on cnss.gov.lb - one titled "covered at 80%"
and one "covered at 95%" (chronic / incurable conditions). Both are exported from Excel by
Acrobat PDFMaker, so `pdftotext -layout` recovers the table faithfully. The management
command does the PDF-to-text step; everything here works on the already-extracted text so
it stays testable without poppler or network.

Each data row looks like (columns, left to right):

    Code  Reg#  <name / scientific composition>  <strength>  <pack>  UOM  \
        <MoPH price, LBP>  <NSSF price, LBP>  <NSSF category>  <group>  [ST]  \
        <cheapest-equivalent name>  <coverage rate>%

`Code` is MoPH's own product code - the same integer stored on `Medicine.moph_code` - so
matching is an exact keyed lookup, not fuzzy text. The name/strength columns overlap badly
in the extracted layout and are deliberately not relied on.

Prices in the list are in Lebanese pounds at the Banque du Liban peg. The catalog stores
`regulated_price` in USD, so `nssf_reference_price` is converted with `lbp_per_usd`
(default the 89,500 peg) at import time and the divisor is recorded in
`nssf_source_reference`.

The "95%" list is a superset of the "80%" list (it repeats every 80% row and adds the
95% ones), so when both are supplied the higher rate wins per code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from apps.medicines.models import Medicine

SOURCE_PREFIX = "NSSF reimbursable list"
DEFAULT_LBP_PER_USD = Decimal("89500")

# Code ... <two money-or-dash tokens> <category e.g. B / A21> <group e.g. G5> ... <NN>%
_ROW = re.compile(
    r"^\s*(?P<code>\d{3,7})\s+"
    r".*?\s"
    # The MoPH-price column is never used here; tolerate the `#####` pdftotext prints
    # when a very large value overflows the cell.
    r"(?P<moph>[\d,]{3,}|-|#+)\s+"
    r"(?P<nssf>[\d,]{3,}|-)\s+"
    r"(?P<category>[A-Z][0-9]{0,2})\s+"
    r"(?P<group>G[0-9])\b"
    r".*?"
    r"(?P<rate>\d{1,3})%\s*$"
)
_CANDIDATE = re.compile(r"^\s*\d{3,7}\s")


@dataclass(frozen=True)
class NssfRow:
    moph_code: int
    nssf_price_lbp: int | None
    reimbursement_rate: int
    category: str
    group: str


@dataclass
class ParseResult:
    rows: dict[int, NssfRow]  # keyed by moph_code, higher rate wins
    candidate_lines: int
    parsed_lines: int
    unparsed_samples: list[str]

    @property
    def unparsed_lines(self) -> int:
        return self.candidate_lines - self.parsed_lines


@dataclass
class ApplyResult:
    matched: int
    updated: int
    unchanged: int
    unmatched_codes: list[int]
    deactivated: int


def parse_lists(*texts: str) -> ParseResult:
    """Parse one or more `pdftotext -layout` dumps. Later texts win on rate collisions,
    so pass the 80% list before the 95% list."""
    rows: dict[int, NssfRow] = {}
    candidate = 0
    parsed = 0
    unparsed: list[str] = []
    for text in texts:
        for line in text.splitlines():
            if not _CANDIDATE.match(line):
                continue
            candidate += 1
            match = _ROW.match(line.rstrip())
            if not match:
                if len(unparsed) < 25:
                    unparsed.append(line.strip()[:160])
                continue
            parsed += 1
            code = int(match["code"])
            nssf_raw = match["nssf"]
            row = NssfRow(
                moph_code=code,
                nssf_price_lbp=None if nssf_raw == "-" else int(nssf_raw.replace(",", "")),
                reimbursement_rate=int(match["rate"]),
                category=match["category"],
                group=match["group"],
            )
            existing = rows.get(code)
            if existing is None or row.reimbursement_rate >= existing.reimbursement_rate:
                rows[code] = row
    return ParseResult(rows=rows, candidate_lines=candidate, parsed_lines=parsed, unparsed_samples=unparsed)


def _to_usd(lbp: int | None, lbp_per_usd: Decimal) -> Decimal | None:
    if not lbp:
        return None
    return (Decimal(lbp) / lbp_per_usd).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@transaction.atomic
def apply_rows(
    parsed: ParseResult,
    *,
    lbp_per_usd: Decimal = DEFAULT_LBP_PER_USD,
    list_date: str = "2025-04-17",
    deactivate_missing: bool = True,
    dry_run: bool = False,
) -> ApplyResult:
    """Set NSSF coverage on every catalog medicine whose `moph_code` is in `parsed`.

    `deactivate_missing` clears coverage from medicines that were last set by a previous
    run of this importer (identified by `nssf_source_reference`) but are absent from the
    current lists - so a drug dropped by the NSSF stops showing as covered. Manually
    entered coverage (a different source reference, or none) is never touched.
    """
    now = timezone.now()
    by_code = {m.moph_code: m for m in Medicine.objects.filter(moph_code__in=list(parsed.rows))}

    updated = unchanged = 0
    to_save: list[Medicine] = []
    for code, row in parsed.rows.items():
        medicine = by_code.get(code)
        if medicine is None:
            continue
        rate = Decimal(row.reimbursement_rate)
        price = _to_usd(row.nssf_price_lbp, lbp_per_usd)
        peg = format(lbp_per_usd, "f")
        if "." in peg:
            peg = peg.rstrip("0").rstrip(".")
        reference = (
            f"{SOURCE_PREFIX} {list_date} ({row.reimbursement_rate}%), "
            f"cat {row.category}/{row.group}, LBP@{peg}"
        )
        if (
            medicine.nssf_covered
            and medicine.nssf_reimbursement_rate == rate
            and medicine.nssf_reference_price == price
            and medicine.nssf_source_reference == reference
        ):
            unchanged += 1
            continue
        medicine.nssf_covered = True
        medicine.nssf_reimbursement_rate = rate
        medicine.nssf_reference_price = price
        medicine.nssf_source_reference = reference
        medicine.nssf_updated_at = now
        to_save.append(medicine)
        updated += 1

    deactivated = 0
    stale = Medicine.objects.filter(
        nssf_covered=True, nssf_source_reference__startswith=SOURCE_PREFIX
    ).exclude(moph_code__in=list(parsed.rows))
    stale_list = list(stale)
    if deactivate_missing:
        for medicine in stale_list:
            medicine.nssf_covered = False
            medicine.nssf_reference_price = None
            medicine.nssf_reimbursement_rate = None
            medicine.nssf_source_reference = ""
            medicine.nssf_updated_at = now
        deactivated = len(stale_list)

    if not dry_run:
        if to_save:
            Medicine.objects.bulk_update(
                to_save,
                ["nssf_covered", "nssf_reimbursement_rate", "nssf_reference_price", "nssf_source_reference", "nssf_updated_at"],
                batch_size=500,
            )
        if deactivate_missing and stale_list:
            Medicine.objects.bulk_update(
                stale_list,
                ["nssf_covered", "nssf_reference_price", "nssf_reimbursement_rate", "nssf_source_reference", "nssf_updated_at"],
                batch_size=500,
            )

    return ApplyResult(
        matched=len(by_code),
        updated=updated,
        unchanged=unchanged,
        unmatched_codes=sorted(set(parsed.rows) - set(by_code)),
        deactivated=deactivated,
    )
