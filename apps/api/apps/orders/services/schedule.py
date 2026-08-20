from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone

from apps.common.mailer import send_email
from apps.orders.models import Order, RecurringOrder
from apps.orders.services.placement import OrderError, place_order

logger = logging.getLogger(__name__)


def _notify_recurring_failed(recurring: RecurringOrder, error: str) -> None:
    customer = recurring.customer
    if not customer.email:
        return
    try:
        send_email(
            to=[customer.email],
            subject=f"Your recurring order '{recurring.label}' could not be refilled",
            text_body=(
                f"Hi,\n\nWe couldn't generate your next refill for '{recurring.label}': {error}\n"
                f"We'll try again on the next cycle - no action is needed unless the problem persists.\n"
            ),
        )
    except Exception:
        logger.exception("Failed to send recurring-order-failed email for %s", recurring.id)


def advance(recurring: RecurringOrder, *, now=None) -> None:
    now = now or timezone.now()
    next_run = recurring.next_run_at + timedelta(days=recurring.interval_days)
    # Never fall behind: if the worker was down for a while, jump forward to the next future cycle.
    while next_run <= now:
        next_run += timedelta(days=recurring.interval_days)
    recurring.next_run_at = next_run
    recurring.last_run_at = now
    recurring.save(update_fields=["next_run_at", "last_run_at", "occurrences_created", "last_error", "updated_at"])


def run_due_recurring_orders(*, now=None, lead_time_hours: int = 24) -> dict:
    """
    Creates the next order for every due schedule. Sourcing runs fresh each cycle, so a
    refill is not tied to the pharmacy that happened to serve the first one.
    """
    now = now or timezone.now()
    created, failed = [], []
    for recurring in RecurringOrder.objects.filter(is_active=True, next_run_at__lte=now + timedelta(hours=lead_time_hours)).select_related("address", "customer"):
        target = max(recurring.next_run_at, now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        target = target.replace(hour=recurring.preferred_hour)
        if target <= now:
            target = target + timedelta(days=1)
        try:
            order = place_order(
                customer=recurring.customer,
                items=recurring.items,
                address=recurring.address,
                fulfillment_type=Order.FulfillmentType.DELIVERY,
                scheduled_for=target,
                notes=f"Recurring: {recurring.label}",
                source=Order.Source.RECURRING,
                recurring_order=recurring,
                prescription=recurring.prescription,
            )
            recurring.occurrences_created += 1
            recurring.last_error = ""
            advance(recurring, now=now)
            created.append(order.reference)
        except OrderError as exc:
            recurring.last_error = str(exc)[:255]
            advance(recurring, now=now)
            failed.append({"recurring_order": str(recurring.id), "error": str(exc)})
            _notify_recurring_failed(recurring, str(exc))
    return {"created": created, "failed": failed}


def release_due_scheduled_orders(*, now=None, lead_minutes: int = 90) -> list[str]:
    """
    A scheduled order sits out of the dispatch pool until shortly before its window, then
    joins it so the router can batch it with whatever else is going to that neighbourhood.
    """
    now = now or timezone.now()
    released = []
    horizon = now + timedelta(minutes=lead_minutes)
    for order in Order.objects.filter(status=Order.Status.SCHEDULED, released_at__isnull=True, scheduled_for__lte=horizon):
        order.released_at = now
        order.status = Order.Status.PENDING
        order.save(update_fields=["released_at", "status", "updated_at"])
        released.append(order.reference)
    return released
