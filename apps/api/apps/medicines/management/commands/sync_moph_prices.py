"""
Sync regulated medicine prices from the Lebanese MoPH Drugs Public Price List.

    python manage.py sync_moph_prices                 # discover + sync the latest file
    python manage.py sync_moph_prices --loop --every 86400   # run once a day, forever
    python manage.py sync_moph_prices --file path/to/WebMarketed*.xls  # offline/testing

MoPH republishes the entire list whenever the reference exchange rate changes, so every
regulated price moves together - this command just re-syncs the whole thing each pass.
It's idempotent: a pass where nothing changed writes nothing to the database. Safe to
schedule as often as you like; daily is more than enough given how often MoPH actually
publishes updates.
"""

from __future__ import annotations

import time

from django.core.management.base import BaseCommand

from apps.medicines.services.moph_sync import discover_latest_marketed_file_url, run_sync


class Command(BaseCommand):
    help = "Sync Medicine.regulated_price from the official MoPH Drugs Public Price List."

    def add_arguments(self, parser):
        parser.add_argument("--url", help="Explicit WebMarketed*.xls URL (skips auto-discovery).")
        parser.add_argument("--file", help="Local .xls file to sync from instead of downloading.")
        parser.add_argument("--loop", action="store_true", help="Keep running instead of doing a single pass.")
        parser.add_argument("--every", type=int, default=86400, help="Seconds between passes when looping (default: daily).")

    def handle(self, *args, **options):
        while True:
            self.run_once(url=options.get("url"), file_path=options.get("file"))
            if not options["loop"]:
                return
            time.sleep(max(300, options["every"]))

    def run_once(self, *, url, file_path) -> None:
        if file_path:
            with open(file_path, "rb") as f:
                xls_bytes = f.read()
            result = run_sync(xls_bytes=xls_bytes)
        else:
            if not url:
                url = discover_latest_marketed_file_url()
                self.stdout.write(f"discovered latest file: {url}")
            result = run_sync(url=url)

        self.stdout.write(
            self.style.SUCCESS(
                f"processed {result['rows_processed']} rows - "
                f"created {result['created']}, updated {result['updated']}, unchanged {result['unchanged']}"
            )
        )
