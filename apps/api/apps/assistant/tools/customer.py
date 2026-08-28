"""
A signed-in patient's own records.

Every queryset here is anchored on `ctx.user` in its first filter. That anchoring is the
access control - there is no order id, customer id or email parameter anywhere in this module,
so the only records reachable are the ones belonging to whoever holds the auth token.
"""

from __future__ import annotations

from django.utils import timezone

from apps.assistant.tools.base import ToolContext
from apps.eprescriptions.models import Prescription
from apps.orders.models import Order, RecurringOrder

MAX_ROWS = 5


def my_orders(ctx: ToolContext) -> dict:
    """The patient's recent orders, newest first, with where each one has got to."""
    qs = Order.objects.filter(customer=ctx.user).prefetch_related("fulfillments__pharmacy").order_by("-created_at")
    reference = ctx.text("reference")
    if reference:
        # A reference typed by the person narrows their own list; it can never widen it,
        # because the customer filter above is applied first and unconditionally.
        qs = qs.filter(reference__icontains=reference)
    rows = list(qs[:MAX_ROWS])
    return {
        "orders": [
            {
                "reference": order.reference,
                "status": order.get_status_display(),
                "status_code": order.status,
                "fulfillment_type": order.fulfillment_type,
                "total": str(order.total),
                "placed_at": order.created_at.isoformat(),
                "scheduled_for": order.scheduled_for.isoformat() if order.scheduled_for else None,
                "cancelled_reason": order.cancelled_reason,
                "pharmacies": [f.pharmacy.name for f in order.fulfillments.all()],
            }
            for order in rows
        ],
        "total_found": qs.count(),
    }


def my_prescriptions(ctx: ToolContext) -> dict:
    """
    E-prescriptions issued to this patient.

    Matched on the account's own email rather than a name, because `Prescription.patient_email`
    is what the doctor filled in and is the only field that ties a script to an account. A
    patient with no email match simply gets an empty list, which is the correct answer.
    """
    if not ctx.user.email:
        return {"prescriptions": [], "total_found": 0}

    qs = Prescription.objects.filter(patient_email__iexact=ctx.user.email).select_related("doctor").prefetch_related("items").order_by("-issued_at")
    rows = list(qs[:MAX_ROWS])
    now = timezone.now()
    return {
        "prescriptions": [
            {
                "code": item.code,
                "status": item.get_status_display(),
                "status_code": item.status,
                "doctor": item.doctor.full_name,
                "issued_at": item.issued_at.isoformat(),
                "valid_until": item.valid_until.isoformat(),
                "days_left": max(0, (item.valid_until - now).days),
                "is_expired": item.is_expired,
                "items": [
                    {"medicine": line.medicine_text, "prescribed": line.quantity_prescribed, "remaining": line.quantity_remaining, "unit": line.unit}
                    for line in item.items.all()
                ],
            }
            for item in rows
        ],
        "total_found": qs.count(),
    }


def my_refills(ctx: ToolContext) -> dict:
    """Repeat orders this patient has set up, and when each one next runs."""
    qs = RecurringOrder.objects.filter(customer=ctx.user).order_by("next_run_at")
    rows = list(qs[:MAX_ROWS])
    now = timezone.now()
    return {
        "refills": [
            {
                "label": item.label,
                "is_active": item.is_active,
                "interval_days": item.interval_days,
                "next_run_at": item.next_run_at.isoformat(),
                "days_until_next": (item.next_run_at - now).days,
                "last_run_at": item.last_run_at.isoformat() if item.last_run_at else None,
                "item_count": len(item.items or []),
                "last_error": item.last_error,
            }
            for item in rows
        ],
        "total_found": qs.count(),
    }
