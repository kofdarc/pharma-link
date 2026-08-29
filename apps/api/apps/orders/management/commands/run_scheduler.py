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
  5. delivers any pending outgoing webhooks (there is no task queue in this codebase -
     this polling loop is the only place the signed HTTP POST actually happens)
"""

from __future__ import annotations

import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.orders.services.placement import expire_stale_reservations
from apps.orders.services.schedule import release_due_scheduled_orders, run_due_recurring_orders, send_due_refill_reminders


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

        refill_reminders = send_due_refill_reminders()
        if refill_reminders:
            self.stdout.write(f"[{stamp}] queued {refill_reminders} refill reminder(s)")

        from apps.eprescriptions.services.reminders import send_prescription_expiry_reminders

        prescription_reminders = send_prescription_expiry_reminders()
        if prescription_reminders:
            self.stdout.write(f"[{stamp}] queued {prescription_reminders} prescription expiry reminder(s)")

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

        from apps.integrations.services.webhooks import deliver_pending_webhooks

        delivered_webhooks = deliver_pending_webhooks()
        if delivered_webhooks:
            self.stdout.write(f"[{stamp}] attempted {delivered_webhooks} pending webhook delivery(ies)")

        if not (
            released_holds
            or refill_reminders
            or prescription_reminders
            or recurring["created"]
            or released_orders
            or plan
            or delivered_webhooks
        ):
            self.stdout.write(f"[{stamp}] nothing to do")
