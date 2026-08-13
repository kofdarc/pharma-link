"""
Background maintenance for orders and dispatch.

Run this on a timer (cron, Task Scheduler, or a container sidecar). It is idempotent, so
running it more often than needed is harmless:

    python manage.py run_scheduler                # one pass
    python manage.py run_scheduler --loop --every 300

Each pass, in order:
  1. release stock held by orders nobody accepted, so it goes back on sale
  2. generate the next order for any due repeat schedule
  3. move scheduled orders into the dispatch pool as their window approaches
  4. optionally re-plan routes so the new arrivals get batched
"""

from __future__ import annotations

import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.orders.services.placement import expire_stale_reservations
from apps.orders.services.schedule import release_due_scheduled_orders, run_due_recurring_orders


class Command(BaseCommand):
    help = "Release stale stock holds, generate recurring orders, release scheduled orders, and optionally replan routes."

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true", help="Keep running instead of doing a single pass.")
        parser.add_argument("--every", type=int, default=300, help="Seconds between passes when looping.")
        parser.add_argument("--plan", action="store_true", help="Also re-plan delivery routes after each pass.")
        parser.add_argument("--lead-minutes", type=int, default=90, help="How early a scheduled order joins the dispatch pool.")

    def handle(self, *args, **options):
        while True:
            self.run_once(plan=options["plan"], lead_minutes=options["lead_minutes"])
            if not options["loop"]:
                return
            time.sleep(max(30, options["every"]))

    def run_once(self, *, plan: bool, lead_minutes: int) -> None:
        stamp = timezone.now().strftime("%H:%M:%S")

        released_holds = expire_stale_reservations()
        if released_holds:
            self.stdout.write(f"[{stamp}] released {released_holds} expired stock hold(s) back to the shelf")

        recurring = run_due_recurring_orders()
        for reference in recurring["created"]:
            self.stdout.write(self.style.SUCCESS(f"[{stamp}] recurring order created: {reference}"))
        for failure in recurring["failed"]:
            self.stdout.write(self.style.WARNING(f"[{stamp}] recurring order skipped: {failure['error']}"))

        released_orders = release_due_scheduled_orders(lead_minutes=lead_minutes)
        for reference in released_orders:
            self.stdout.write(f"[{stamp}] scheduled order entered the dispatch pool: {reference}")

        if plan:
            from apps.delivery.services.dispatch import plan_and_persist

            result = plan_and_persist()
            summary = result.get("summary") or {}
            self.stdout.write(
                f"[{stamp}] {result['detail']} "
                f"({summary.get('optimised_distance_km', 0)} km vs {summary.get('naive_distance_km', 0)} km naive)"
            )

        if not (released_holds or recurring["created"] or released_orders or plan):
            self.stdout.write(f"[{stamp}] nothing to do")
