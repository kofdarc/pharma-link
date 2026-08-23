from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from apps.audit.services import write_audit_log
from apps.insurance.models import InsuranceClaim, InsurancePlan

TWO_PLACES = Decimal("0.01")


class InsuranceError(Exception):
    pass


def compute_copay(plan: InsurancePlan, amount: Decimal) -> tuple[Decimal, Decimal]:
    """
    Returns (patient_copay, covered_amount) for billing `amount` against `plan`. The
    insurer covers `coverage_percentage`, but the patient never pays less than
    `copay_minimum` - and the insurer's share is re-clamped so it can never go negative
    when the floor exceeds what percentage coverage alone would have left the patient
    owing.
    """
    amount = Decimal(amount)
    covered_by_percentage = (amount * plan.coverage_percentage / Decimal("100")).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    patient_copay = max(amount - covered_by_percentage, plan.copay_minimum)
    patient_copay = min(patient_copay, amount).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    covered_amount = (amount - patient_copay).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    return patient_copay, covered_amount


@transaction.atomic
def submit_claim_for_fulfillment(*, fulfillment, policy, user=None) -> InsuranceClaim:
    if hasattr(fulfillment, "insurance_claim"):
        raise InsuranceError("This fulfillment already has an insurance claim on file.")
    billed_amount = fulfillment.subtotal
    patient_copay, covered_amount = compute_copay(policy.plan, billed_amount)
    claim = InsuranceClaim.objects.create(
        order_fulfillment=fulfillment,
        policy=policy,
        pharmacy=fulfillment.pharmacy,
        billed_amount=billed_amount,
        covered_amount=covered_amount,
        patient_copay=patient_copay,
    )
    write_audit_log(
        actor_user=user,
        pharmacy=fulfillment.pharmacy,
        action="insurance.claim_submitted",
        entity_type="InsuranceClaim",
        entity_id=claim.id,
        summary=f"Claim submitted for {fulfillment.order.reference} @ {fulfillment.pharmacy.name}",
        after_data={"billed_amount": str(billed_amount), "covered_amount": str(covered_amount), "patient_copay": str(patient_copay)},
    )
    return claim


@transaction.atomic
def submit_claim_for_sale(*, sale, policy, user=None) -> InsuranceClaim:
    if hasattr(sale, "insurance_claim"):
        raise InsuranceError("This sale already has an insurance claim on file.")
    billed_amount = sale.total
    patient_copay, covered_amount = compute_copay(policy.plan, billed_amount)
    claim = InsuranceClaim.objects.create(
        sale=sale,
        policy=policy,
        pharmacy=sale.pharmacy,
        billed_amount=billed_amount,
        covered_amount=covered_amount,
        patient_copay=patient_copay,
    )
    write_audit_log(
        actor_user=user,
        pharmacy=sale.pharmacy,
        action="insurance.claim_submitted",
        entity_type="InsuranceClaim",
        entity_id=claim.id,
        summary=f"Claim submitted for invoice {sale.invoice_number}",
        after_data={"billed_amount": str(billed_amount), "covered_amount": str(covered_amount), "patient_copay": str(patient_copay)},
    )
    return claim


_ALLOWED_TRANSITIONS = {
    InsuranceClaim.Status.SUBMITTED: {InsuranceClaim.Status.APPROVED, InsuranceClaim.Status.REJECTED, InsuranceClaim.Status.CANCELLED},
    InsuranceClaim.Status.APPROVED: {InsuranceClaim.Status.PAID},
    InsuranceClaim.Status.REJECTED: set(),
    InsuranceClaim.Status.PAID: set(),
    InsuranceClaim.Status.CANCELLED: set(),
}


@transaction.atomic
def update_claim_status(*, claim: InsuranceClaim, status: str, approval_code: str = "", rejection_reason: str = "", user=None) -> InsuranceClaim:
    locked = InsuranceClaim.objects.select_for_update().get(id=claim.id)
    if status not in _ALLOWED_TRANSITIONS.get(locked.status, set()):
        raise InsuranceError(f"Cannot move a claim from {locked.status} to {status}.")
    locked.status = status
    if status == InsuranceClaim.Status.APPROVED:
        locked.approval_code = approval_code
        locked.approved_at = timezone.now()
    elif status == InsuranceClaim.Status.REJECTED:
        locked.rejection_reason = rejection_reason
    elif status == InsuranceClaim.Status.CANCELLED:
        locked.rejection_reason = rejection_reason
    elif status == InsuranceClaim.Status.PAID:
        locked.paid_at = timezone.now()
    locked.save(update_fields=["status", "approval_code", "rejection_reason", "approved_at", "paid_at", "updated_at"])
    write_audit_log(
        actor_user=user,
        pharmacy=locked.pharmacy,
        action="insurance.claim_status_changed",
        entity_type="InsuranceClaim",
        entity_id=locked.id,
        summary=f"Claim moved to {status}",
        after_data={"status": status},
    )
    return locked


@transaction.atomic
def cancel_claim_for_fulfillment(*, fulfillment, user=None, reason: str = "") -> InsuranceClaim | None:
    """
    Called when a fulfillment is rejected or its order is cancelled - the dispensing this
    claim was billed for never happened. Only a still-SUBMITTED claim is cancelled: once an
    insurer has already APPROVED or PAID it, that is a real external claim staff need to
    unwind by hand via the claims page, not something this can silently undo.
    """
    claim = getattr(fulfillment, "insurance_claim", None)
    if claim is None or claim.status != InsuranceClaim.Status.SUBMITTED:
        return None
    return update_claim_status(claim=claim, status=InsuranceClaim.Status.CANCELLED, rejection_reason=reason, user=user)
