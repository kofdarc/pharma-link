from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit.services import write_audit_log
from apps.eprescriptions.models import Doctor, Prescription, PrescriptionItem
from apps.eprescriptions.services import mailer, tokens
from apps.medicines.models import Medicine


class IssueError(Exception):
    pass


@transaction.atomic
def issue_prescription(*, doctor: Doctor, patient: dict, items: list[dict], diagnosis_note: str = "", validity_days: int | None = None) -> tuple[Prescription, str, str]:
    """
    Creates a prescription and returns (prescription, secret, pin).
    The secret and PIN are returned once and never recoverable afterwards - only their hashes are stored.
    """
    if not doctor.is_activated or not doctor.is_active:
        raise IssueError("This licence is not active for issuing prescriptions.")
    if not items:
        raise IssueError("A prescription needs at least one item.")

    validity_days = validity_days or settings.PRESCRIPTION_VALIDITY_DAYS
    secret = tokens.generate_secret()
    pin = tokens.generate_pin()

    for attempt in range(5):
        code = tokens.generate_code()
        try:
            with transaction.atomic():
                prescription = Prescription.objects.create(
                    doctor=doctor,
                    code=code,
                    secret_hash=tokens.hash_value(secret),
                    pin_hash=tokens.hash_pin(pin),
                    patient_name=patient["patient_name"],
                    patient_email=patient.get("patient_email", ""),
                    patient_phone=patient.get("patient_phone", ""),
                    patient_date_of_birth=patient.get("patient_date_of_birth"),
                    diagnosis_note=diagnosis_note,
                    valid_until=timezone.now() + timedelta(days=validity_days),
                )
            break
        except IntegrityError:
            if attempt == 4:
                raise IssueError("Could not allocate a prescription code. Please retry.")
    else:  # pragma: no cover - loop always breaks or raises
        raise IssueError("Could not allocate a prescription code. Please retry.")

    for raw in items:
        medicine = None
        if raw.get("medicine"):
            medicine = Medicine.objects.filter(id=raw["medicine"], is_active=True).first()
        PrescriptionItem.objects.create(
            prescription=prescription,
            medicine=medicine,
            medicine_text=raw.get("medicine_text") or (str(medicine) if medicine else ""),
            quantity_prescribed=int(raw["quantity_prescribed"]),
            unit=raw.get("unit") or "unit",
            dosage_instructions=raw.get("dosage_instructions", ""),
            allow_generic_substitution=bool(raw.get("allow_generic_substitution", True)),
        )

    write_audit_log(
        actor_user=doctor.user,
        action="eprescriptions.issued",
        entity_type="Prescription",
        entity_id=prescription.id,
        summary=f"Dr. {doctor.full_name} issued {prescription.code} ({len(items)} items)",
        after_data={"code": prescription.code, "items": len(items), "valid_until": prescription.valid_until.isoformat()},
    )

    if prescription.patient_email:
        mailer.send_prescription_email(prescription, secret=secret, pin=pin)
        prescription.email_sent_at = timezone.now()
        prescription.save(update_fields=["email_sent_at", "updated_at"])

    return prescription, secret, pin


@transaction.atomic
def cancel_prescription(*, prescription: Prescription, reason: str = "") -> Prescription:
    prescription = Prescription.objects.select_for_update().get(id=prescription.id)
    if prescription.status == Prescription.Status.FULLY_DISPENSED:
        raise IssueError("A fully dispensed prescription cannot be cancelled.")
    prescription.status = Prescription.Status.CANCELLED
    prescription.cancelled_at = timezone.now()
    prescription.cancellation_reason = reason
    prescription.save(update_fields=["status", "cancelled_at", "cancellation_reason", "updated_at"])
    write_audit_log(
        actor_user=prescription.doctor.user,
        action="eprescriptions.cancelled",
        entity_type="Prescription",
        entity_id=prescription.id,
        summary=f"Cancelled {prescription.code}",
        after_data={"reason": reason},
    )
    return prescription
