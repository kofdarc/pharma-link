"""
A prescribing doctor's own workload.

Anchored on `ctx.user.doctor_profile`, so the reachable set is exactly the prescriptions this
doctor wrote and the renewal requests raised against them. A doctor whose account has no
activated Doctor record reaches nothing, which is the same answer the prescribing screens give.
"""

from __future__ import annotations

from django.db.models import Q
from django.utils import timezone

from apps.assistant.tools.base import ToolContext
from apps.eprescriptions.models import Prescription, PrescriptionRenewalRequest
from apps.medicines.services.search import search_medicines

MAX_ROWS = 5


def _profile(ctx: ToolContext):
    return getattr(ctx.user, "doctor_profile", None)


def catalogue_lookup(ctx: ToolContext) -> dict:
    """
    Registration facts for a product: form, strength, schedule, whether it is prescription-only.

    A catalogue read and nothing more. It reports what the MoPH-sourced record says; it does
    not rank, compare or suggest alternatives, because that would be a substitution
    recommendation wearing a lookup's clothes.
    """
    query = ctx.text("query")
    if not query:
        return {"query": "", "matches": []}
    matches = list(search_medicines(query, active_only=True, limit=MAX_ROWS))
    return {
        "query": query,
        "matches": [
            {
                "brand_name": item.brand_name,
                "generic_name": item.generic_name,
                "strength": item.strength,
                "form": item.form,
                "route": item.route,
                "manufacturer": item.manufacturer,
                "requires_prescription": item.requires_prescription,
                "drug_schedule": item.get_drug_schedule_display(),
                "market_status": item.get_market_status_display(),
                "is_price_regulated": item.is_price_regulated,
            }
            for item in matches
        ],
    }


def my_prescriptions(ctx: ToolContext) -> dict:
    """Prescriptions this doctor issued, newest first."""
    doctor = _profile(ctx)
    if doctor is None:
        return {"prescriptions": [], "total_found": 0}

    qs = Prescription.objects.filter(doctor=doctor).prefetch_related("items").order_by("-issued_at")
    query = ctx.text("query")
    if query:
        qs = qs.filter(Q(patient_name__icontains=query) | Q(code__icontains=query))
    if ctx.slots.get("expiring_only"):
        qs = qs.filter(valid_until__lte=timezone.now() + timezone.timedelta(days=7), status=Prescription.Status.ISSUED)

    rows = list(qs[:MAX_ROWS])
    now = timezone.now()
    return {
        "prescriptions": [
            {
                "code": item.code,
                "patient_name": item.patient_name,
                "status": item.get_status_display(),
                "issued_at": item.issued_at.isoformat(),
                "valid_until": item.valid_until.isoformat(),
                "days_left": max(0, (item.valid_until - now).days),
                "item_count": item.items.count(),
            }
            for item in rows
        ],
        "total_found": qs.count(),
    }


def renewal_requests(ctx: ToolContext) -> dict:
    """Renewal requests pharmacies have raised against this doctor's prescriptions."""
    doctor = _profile(ctx)
    if doctor is None:
        return {"requests": [], "pending_count": 0, "total_found": 0}

    qs = (
        PrescriptionRenewalRequest.objects.filter(prescription__doctor=doctor)
        .select_related("prescription", "requested_by_pharmacy")
        .order_by("-created_at")
    )
    pending = qs.filter(status=PrescriptionRenewalRequest.Status.PENDING)
    rows = list(pending[:MAX_ROWS])
    return {
        "requests": [
            {
                "prescription_code": item.prescription.code,
                "patient_name": item.prescription.patient_name,
                "pharmacy": item.requested_by_pharmacy.name,
                "note": item.note[:200],
                "requested_at": item.created_at.isoformat(),
                "waiting_days": (timezone.now() - item.created_at).days,
            }
            for item in rows
        ],
        "pending_count": pending.count(),
        "total_found": qs.count(),
    }


def my_patients(ctx: ToolContext) -> dict:
    """
    People this doctor has prescribed for, grouped the same way the patients screen groups
    them - by the patient details recorded on each prescription, since there is no separate
    patient record on this platform.
    """
    doctor = _profile(ctx)
    if doctor is None:
        return {"patients": [], "total_found": 0}

    qs = Prescription.objects.filter(doctor=doctor)
    query = ctx.text("query")
    if query:
        qs = qs.filter(Q(patient_name__icontains=query) | Q(patient_email__icontains=query))

    grouped: dict[str, dict] = {}
    for item in qs.order_by("-issued_at")[:200]:
        key = (item.patient_email or item.patient_name).lower()
        entry = grouped.setdefault(key, {"name": item.patient_name, "email": item.patient_email, "prescription_count": 0, "last_issued_at": None})
        entry["prescription_count"] += 1
        if entry["last_issued_at"] is None:
            entry["last_issued_at"] = item.issued_at.isoformat()

    patients = list(grouped.values())
    return {"patients": patients[:MAX_ROWS], "total_found": len(patients)}
