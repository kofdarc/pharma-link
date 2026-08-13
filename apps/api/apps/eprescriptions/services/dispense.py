from __future__ import annotations

from django.db import transaction

from apps.audit.services import write_audit_log
from apps.eprescriptions.models import (
    Prescription,
    PrescriptionAccessLog,
    PrescriptionDispense,
    PrescriptionDispenseItem,
    PrescriptionItem,
)
from apps.eprescriptions.services.access import client_ip, log_access


class DispenseError(Exception):
    pass


@transaction.atomic
def dispense_prescription(*, prescription: Prescription, lines: list[dict], pharmacy_details: dict, pharmacy=None, request=None) -> PrescriptionDispense:
    """
    Consumes part or all of a prescription. Partial dispensing is first-class: a patient
    can get two of four items here and the rest elsewhere, and the remaining quantities
    stay claimable exactly once each.
    """
    prescription = Prescription.objects.select_for_update().get(id=prescription.id)
    if not prescription.is_consumable:
        raise DispenseError(f"This prescription is {prescription.get_status_display().lower()} and cannot be dispensed.")

    requested = {str(line["prescription_item"]): int(line["quantity"]) for line in lines if int(line.get("quantity", 0)) > 0}
    if not requested:
        raise DispenseError("Enter at least one quantity to dispense.")

    items = {str(item.id): item for item in PrescriptionItem.objects.select_for_update().filter(prescription=prescription)}
    unknown = set(requested) - set(items)
    if unknown:
        raise DispenseError("One or more items do not belong to this prescription.")

    for item_id, quantity in requested.items():
        item = items[item_id]
        if quantity > item.quantity_remaining:
            raise DispenseError(f"{item.medicine_text}: only {item.quantity_remaining} {item.unit} remain on this prescription.")

    dispense = PrescriptionDispense.objects.create(
        prescription=prescription,
        pharmacy=pharmacy,
        pharmacy_name=pharmacy.name if pharmacy else pharmacy_details["pharmacy_name"],
        pharmacist_name=pharmacy_details["pharmacist_name"],
        pharmacist_license=pharmacy_details.get("pharmacist_license", ""),
        contact_phone=pharmacy_details.get("contact_phone", ""),
        notes=pharmacy_details.get("notes", ""),
        ip_address=client_ip(request),
    )

    for item_id, quantity in requested.items():
        item = items[item_id]
        PrescriptionDispenseItem.objects.create(
            dispense=dispense,
            prescription_item=item,
            quantity=quantity,
            substituted_with=next((line.get("substituted_with", "") for line in lines if str(line["prescription_item"]) == item_id), ""),
        )
        item.quantity_dispensed += quantity
        item.save(update_fields=["quantity_dispensed", "updated_at"])

    prescription.refresh_from_db()
    prescription.recompute_status()
    prescription.save(update_fields=["status", "updated_at"])

    log_access(
        prescription=prescription,
        code_attempted=prescription.code,
        action=PrescriptionAccessLog.Action.DISPENSE,
        method=pharmacy_details.get("method", ""),
        request=request,
        detail=f"{dispense.pharmacy_name}: {sum(requested.values())} units",
    )
    write_audit_log(
        actor_user=None,
        pharmacy=pharmacy,
        action="eprescriptions.dispensed",
        entity_type="Prescription",
        entity_id=prescription.id,
        summary=f"{dispense.pharmacy_name} dispensed against {prescription.code}",
        after_data={"status": prescription.status, "units": sum(requested.values())},
        ip_address=client_ip(request),
    )
    return dispense
