"""
Full MoPH catalog sync: the online Lebanon National Drugs Database (primary source
for MARKETED products) plus the WebNonMarketed*.xls file (NON_MARKETED products),
reconciled against WebMarketed*.xls for its USD price and as a scrape-completeness
check. See apps/medicines/services/moph_sync.py for the precedence/identity rules.

    python manage.py sync_moph_catalog                       # full crawl + sync
    python manage.py sync_moph_catalog --loop --every 86400   # run once a day, forever
    python manage.py sync_moph_catalog --letters A,B --max-pages-per-letter 1 \
        --skip-non-marketed-excel --skip-marketed-excel-check  # fast, online-only dev smoke test

--letters/--max-pages-per-letter only scope the online crawl (it's paginated); the
Excel files are single downloads with no such scoping, so a dev smoke test that
wants to touch ONLY the online crawl must also pass --skip-non-marketed-excel
(and usually --skip-marketed-excel-check) or it will still run a full,
production-sized Excel sync against whatever database you're pointed at.

This is a separate command from `sync_moph_prices` (which keeps working unchanged,
for a fast price-only refresh); this one is the full catalog pipeline and is
expected to take much longer (a full crawl is on the order of 5,000-8,000 HTTP
requests to moph.gov.lb).
"""

from __future__ import annotations

import time

from django.core.management.base import BaseCommand, CommandError

from apps.medicines.services.moph_sync import run_full_sync


class Command(BaseCommand):
    help = "Sync the Medicine catalog from MoPH's online drug database + Non-Marketed/Marketed Excel files."

    def add_arguments(self, parser):
        parser.add_argument("--letters", help="Comma-separated starting letters to crawl (default: A-Z).")
        parser.add_argument("--max-pages-per-letter", type=int, help="Cap pages fetched per letter (for dev/testing).")
        parser.add_argument("--delay", type=float, default=0.3, help="Seconds to sleep between MoPH requests (default: 0.3).")
        parser.add_argument("--skip-marketed-excel-check", action="store_true", help="Skip the Marketed Excel USD-price/reconciliation pass.")
        parser.add_argument("--skip-non-marketed-excel", action="store_true", help="Skip the Non-Marketed Excel pass entirely (dev/testing only - it is otherwise always a full, unscoped download).")
        parser.add_argument("--loop", action="store_true", help="Keep running instead of doing a single pass.")
        parser.add_argument("--every", type=int, default=86400, help="Seconds between passes when looping (default: daily).")

    def handle(self, *args, **options):
        letters = [letter.strip().upper() for letter in options["letters"].split(",")] if options.get("letters") else None
        while True:
            self.run_once(
                letters=letters,
                max_pages_per_letter=options.get("max_pages_per_letter"),
                delay_seconds=options["delay"],
                skip_marketed_excel_check=options["skip_marketed_excel_check"],
                skip_non_marketed_excel=options["skip_non_marketed_excel"],
            )
            if not options["loop"]:
                return
            time.sleep(max(300, options["every"]))

    def run_once(self, *, letters, max_pages_per_letter, delay_seconds, skip_marketed_excel_check, skip_non_marketed_excel) -> None:
        result = run_full_sync(
            letters=letters,
            max_pages_per_letter=max_pages_per_letter,
            delay_seconds=delay_seconds,
            skip_marketed_excel_check=skip_marketed_excel_check,
            skip_non_marketed_excel=skip_non_marketed_excel,
        )

        if result.get("aborted"):
            raise CommandError(
                f"MoPH catalog sync aborted: {result['reason']} "
                f"(online crawl found only {result['online_products_found']} products). Nothing was written."
            )

        self.stdout.write(
            self.style.SUCCESS(
                "MoPH sync completed\n"
                f"Created: {result['created']} | Updated: {result['updated']} | Unchanged: {result['unchanged']}\n"
                f"Marketed: {result['marketed']} | Non-marketed: {result['non_marketed']}\n"
                f"Changed MARKETED -> NON_MARKETED: {result['changed_marketed_to_non_marketed']} | "
                f"Changed NON_MARKETED -> MARKETED: {result['changed_non_marketed_to_marketed']}\n"
                f"Duplicates skipped: {result['duplicates_skipped']} | Invalid rows: {result['invalid_rows']}"
            )
        )
