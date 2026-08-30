"""
Import NSSF (National Social Security Fund) medicine reimbursement coverage from the
official CNSS lists.

    # the two PDF lists shipped in the repo
    python manage.py import_nssf_coverage \
        --file apps/api/data/nssf/nssf_list_80pct_2025-04.pdf \
        --file apps/api/data/nssf/nssf_list_95pct_2025-04.pdf

    python manage.py import_nssf_coverage --file list80.txt --file list95.txt --dry-run

Accepts .pdf (converted in-process with `pdftotext -layout`, poppler required) or an
already-extracted .txt. Pass the 80% list before the 95% list; the 95% list repeats the
80% rows and the higher rate wins per medicine.

Prices in the lists are Lebanese pounds; `--lbp-per-usd` (default 89500, the BdL peg)
converts them to the USD unit the catalog stores `regulated_price` in.

Idempotent: a second run with the same files writes nothing. Coverage set by a previous
run of this command is cleared for any medicine no longer on the lists; manually entered
coverage is left alone.
"""

from __future__ import annotations

import subprocess
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.medicines.services.nssf_import import DEFAULT_LBP_PER_USD, apply_rows, parse_lists


class Command(BaseCommand):
    help = "Import NSSF reimbursement coverage (covered flag, rate, reference price) from the CNSS lists."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            action="append",
            dest="files",
            required=True,
            metavar="PATH",
            help="An NSSF list (.pdf or .txt). Repeat for the 80%% and 95%% lists; pass 80%% first.",
        )
        parser.add_argument("--list-date", default="2025-04-17", help="Effective date of the lists, for the source reference.")
        parser.add_argument(
            "--lbp-per-usd",
            type=Decimal,
            default=DEFAULT_LBP_PER_USD,
            help="Divisor applied to the LBP reference prices (default: 89500).",
        )
        parser.add_argument(
            "--keep-missing",
            action="store_true",
            help="Do not clear coverage from medicines that dropped off the lists since the last import.",
        )
        parser.add_argument("--dry-run", action="store_true", help="Report what would change without writing.")

    def handle(self, *args, **options):
        texts = [self._read(Path(path)) for path in options["files"]]
        parsed = parse_lists(*texts)

        self.stdout.write(
            f"parsed {parsed.parsed_lines}/{parsed.candidate_lines} rows "
            f"({parsed.unparsed_lines} unparsed) -> {len(parsed.rows)} distinct medicines"
        )
        for sample in parsed.unparsed_samples[:5]:
            self.stdout.write(self.style.WARNING(f"  unparsed: {sample}"))

        result = apply_rows(
            parsed,
            lbp_per_usd=options["lbp_per_usd"],
            list_date=options["list_date"],
            deactivate_missing=not options["keep_missing"],
            dry_run=options["dry_run"],
        )

        verb = "would set" if options["dry_run"] else "set"
        self.stdout.write(
            f"{verb} coverage on {result.updated} medicines "
            f"({result.unchanged} already current, {result.matched} matched by MoPH code, "
            f"{len(result.unmatched_codes)} list codes have no catalog entry, "
            f"{result.deactivated} dropped medicines cleared)"
        )
        if result.unmatched_codes:
            preview = ", ".join(str(code) for code in result.unmatched_codes[:15])
            self.stdout.write(self.style.NOTICE(f"  unmatched MoPH codes (first 15): {preview}"))
        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("dry run - nothing written"))
        else:
            self.stdout.write(self.style.SUCCESS("done"))

    def _read(self, path: Path) -> str:
        if not path.exists():
            raise CommandError(f"file not found: {path}")
        if path.suffix.lower() != ".pdf":
            return path.read_text(encoding="utf-8", errors="replace")
        try:
            completed = subprocess.run(
                ["pdftotext", "-layout", str(path), "-"],
                capture_output=True,
                check=True,
            )
        except FileNotFoundError as exc:
            raise CommandError("pdftotext not found - install poppler, or pass a pre-extracted .txt file.") from exc
        except subprocess.CalledProcessError as exc:
            raise CommandError(f"pdftotext failed on {path}: {exc.stderr.decode('utf-8', 'replace')}") from exc
        return completed.stdout.decode("utf-8", errors="replace")
