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
from apps.inventory.services.coverage import pharmacies_covering
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


def prescription_coverage(ctx: ToolContext) -> dict:
    """
    The nearest pharmacy that can fill this patient's whole prescription in one visit.

    Anchored on `ctx.user` the same way every other handler in this module is: the
    prescription is found by the account's own email before anything else happens, so a code
    typed into the message can only narrow that person's own scripts, never reach somebody
    else's. A code that is not theirs simply matches nothing.

    Two things this deliberately does not do. It does not reserve stock - the shopper is
    being told what is possible, not being promised it, and the checkout planner
    (apps.orders.services.sourcing) is the only thing in this codebase that holds units. And
    it does not silently substitute: a prescription line whose product is not in the
    catalogue is reported as unmatched rather than resolved to something similar, because
    "close enough" is a clinical judgement and this assistant does not make those.
    """
    if not ctx.user.email:
        return {"prescription": None, "reason": "no_email"}

    qs = (
        Prescription.objects.filter(patient_email__iexact=ctx.user.email, valid_until__gt=timezone.now())
        .exclude(status__in=[Prescription.Status.CANCELLED, Prescription.Status.FULLY_DISPENSED, Prescription.Status.EXPIRED])
        .select_related("doctor")
        .prefetch_related("items__medicine")
        .order_by("-issued_at")
    )
    code = ctx.text("reference") or ctx.text("query")
    if code:
        narrowed = qs.filter(code__icontains=code)
        qs = narrowed if narrowed.exists() else qs

    prescription = qs.first()
    if prescription is None:
        return {"prescription": None, "reason": "none_valid"}

    needs: dict[str, int] = {}
    matched, unmatched = [], []
    for line in prescription.items.all():
        outstanding = max(0, line.quantity_prescribed - line.quantity_dispensed)
        if outstanding <= 0:
            continue
        if line.medicine_id is None:
            # Written free-hand by the doctor and never linked to a catalogue product. There
            # is nothing to look up stock against, and guessing from the text is exactly the
            # substitution this must not do.
            unmatched.append({"medicine": line.medicine_text, "outstanding": outstanding})
            continue
        matched.append({"medicine": line.medicine.brand_name, "outstanding": outstanding, "requires_prescription": line.medicine.requires_prescription})
        needs[str(line.medicine_id)] = needs.get(str(line.medicine_id), 0) + outstanding

    latitude, longitude = ctx.coordinates
    rows = pharmacies_covering(needs=needs, latitude=latitude, longitude=longitude) if needs else []
    full = [row for row in rows if row["covers_everything"]]
    return {
        "prescription": {
            "code": prescription.code,
            "doctor": prescription.doctor.full_name,
            "status": prescription.get_status_display(),
            "valid_until": prescription.valid_until.isoformat(),
            "days_left": max(0, (prescription.valid_until - timezone.now()).days),
        },
        "located": latitude is not None,
        "lines_outstanding": len(matched),
        "matched": matched,
        "unmatched": unmatched,
        "full_coverage": full[:MAX_ROWS],
        "partial_coverage": [row for row in rows if not row["covers_everything"]][:MAX_ROWS],
        "total_found": len(rows),
    }
