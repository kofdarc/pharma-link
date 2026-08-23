from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.audit.services import write_audit_log
from apps.eprescriptions.models import Prescription, PrescriptionRenewalRequest
from apps.eprescriptions.services.issue import issue_prescription
from apps.pharmacies.models import Pharmacy


class RenewalError(Exception):
    pass


def _pharmacy_has_standing(prescription: Prescription, pharmacy: Pharmacy) -> bool:
    """A pharmacy may ask for a renewal only if it has legitimate prior contact with this
    prescription - either it's the target pharmacy, or it has already dispensed against it."""
    if prescription.target_pharmacy_id == pharmacy.id:
        return True
    return prescription.dispenses.filter(pharmacy=pharmacy).exists()


@transaction.atomic
def request_renewal(*, prescription: Prescription, pharmacy: Pharmacy, requested_by_user, note: str = "") -> PrescriptionRenewalRequest:
    if prescription.status == Prescription.Status.CANCELLED:
        raise RenewalError(_("This prescription was cancelled and cannot be renewed."))
    if not _pharmacy_has_standing(prescription, pharmacy):
        raise RenewalError(_("Your pharmacy has no record of this prescription."))
    if prescription.renewal_requests.filter(status=PrescriptionRenewalRequest.Status.PENDING).exists():
        raise RenewalError(_("A renewal request is already pending for this prescription."))

    renewal_request = PrescriptionRenewalRequest.objects.create(
        prescription=prescription,
        requested_by_pharmacy=pharmacy,
        requested_by_user=requested_by_user,
        note=note,
    )
    write_audit_log(
        actor_user=requested_by_user,
        pharmacy=pharmacy,
        action="eprescriptions.renewal_requested",
        entity_type="PrescriptionRenewalRequest",
        entity_id=renewal_request.id,
        summary=f"{pharmacy.name} requested a renewal of {prescription.code}",
        after_data={"note": note},
    )
    if prescription.target_pharmacy_id:
        from apps.messaging.services import get_or_create_conversation, send_message

        conversation = get_or_create_conversation(prescription=prescription)
        body = f"{pharmacy.name} requested a renewal of {prescription.code}."
        if note:
            body += f" Note: {note}"
        send_message(conversation=conversation, sender=requested_by_user, body=body)
    return renewal_request


@transaction.atomic
def respond_to_renewal(*, renewal_request: PrescriptionRenewalRequest, approve: bool, response_note: str = "") -> PrescriptionRenewalRequest:
    renewal_request = PrescriptionRenewalRequest.objects.select_for_update().get(id=renewal_request.id)
    if renewal_request.status != PrescriptionRenewalRequest.Status.PENDING:
        raise RenewalError(_("This renewal request was already answered."))

    original = renewal_request.prescription
    if approve:
        items = [
            {
                "medicine": str(item.medicine_id) if item.medicine_id else None,
                "medicine_text": item.medicine_text,
                "quantity_prescribed": item.quantity_prescribed,
                "unit": item.unit,
                "dosage_instructions": item.dosage_instructions,
                "allow_generic_substitution": item.allow_generic_substitution,
            }
            for item in original.items.all()
        ]
        new_prescription, _secret, _pin = issue_prescription(
            doctor=original.doctor,
            patient={
                "patient_name": original.patient_name,
                "patient_email": original.patient_email,
                "patient_phone": original.patient_phone,
                "patient_date_of_birth": original.patient_date_of_birth,
            },
            items=items,
            diagnosis_note=original.diagnosis_note,
            target_pharmacy=renewal_request.requested_by_pharmacy,
            renewed_from=original,
        )
        renewal_request.new_prescription = new_prescription
        renewal_request.status = PrescriptionRenewalRequest.Status.APPROVED
    else:
        renewal_request.status = PrescriptionRenewalRequest.Status.DENIED

    renewal_request.response_note = response_note
    renewal_request.responded_at = timezone.now()
    renewal_request.save(update_fields=["status", "response_note", "responded_at", "new_prescription", "updated_at"])

    write_audit_log(
        actor_user=original.doctor.user,
        action="eprescriptions.renewal_responded",
        entity_type="PrescriptionRenewalRequest",
        entity_id=renewal_request.id,
        summary=f"Renewal of {original.code} {'approved' if approve else 'denied'}",
        after_data={"response_note": response_note},
    )
    # Notify over the messaging thread only when one is possible: an approval always has one
    # (the new prescription is targeted at the requesting pharmacy), a denial only has one if
    # that pharmacy already had a channel via the original prescription. Otherwise the
    # pharmacy still sees the outcome by polling its renewal-requests list.
    from apps.messaging.services import get_or_create_conversation, send_message

    if approve:
        conversation = get_or_create_conversation(prescription=renewal_request.new_prescription)
        body = f"Renewal approved. New prescription {renewal_request.new_prescription.code} was issued."
        send_message(conversation=conversation, sender=original.doctor.user, body=body)
    elif original.target_pharmacy_id == renewal_request.requested_by_pharmacy_id:
        conversation = get_or_create_conversation(prescription=original)
        body = "Renewal denied."
        if response_note:
            body += f" Reason: {response_note}"
        send_message(conversation=conversation, sender=original.doctor.user, body=body)
    return renewal_request
