from __future__ import annotations

from django.db import transaction

from apps.audit.services import write_audit_log
from apps.billing.models import PlatformServiceFee


def charge_platform_service_fee(*, fulfillment) -> PlatformServiceFee | None:
    """
    Called when a pharmacy accepts an order fulfillment - a "request submitted through the
    platform" in the mentors' revenue-model decision. Returns None (no charge) if the
    pharmacy has no active subscription or its plan's per-request fee is zero. Idempotent:
    a fulfillment can only ever carry one fee.
    """
    if hasattr(fulfillment, "platform_service_fee"):
        return fulfillment.platform_service_fee
    subscription = getattr(fulfillment.pharmacy, "subscription", None)
    if subscription is None or subscription.status != subscription.Status.ACTIVE:
        return None
    if subscription.plan.service_fee_per_request <= 0:
        return None
    return PlatformServiceFee.objects.create(
        pharmacy=fulfillment.pharmacy,
        fulfillment=fulfillment,
        amount=subscription.plan.service_fee_per_request,
    )


@transaction.atomic
def waive_service_fee(*, fulfillment, reason: str = "", user=None) -> None:
    """
    A fulfillment is charged the moment it is accepted (see charge_platform_service_fee
    above). If it is later rejected - the pharmacy accepted, then could not actually fill it
    - the pharmacy should not be left owing a fee for a request it never fulfilled.
    """
    fee = PlatformServiceFee.objects.select_for_update().filter(fulfillment=fulfillment).exclude(status=PlatformServiceFee.Status.WAIVED).first()
    if fee is None:
        return
    fee.status = PlatformServiceFee.Status.WAIVED
    fee.save(update_fields=["status", "updated_at"])
    write_audit_log(
        actor_user=user,
        pharmacy=fee.pharmacy,
        action="billing.service_fee_waived",
        entity_type="PlatformServiceFee",
        entity_id=fee.id,
        summary=f"Waived service fee for {fulfillment.order.reference}" + (f": {reason}" if reason else ""),
    )


@transaction.atomic
def mark_service_fee_paid(*, fee: PlatformServiceFee, user=None) -> PlatformServiceFee:
    locked = PlatformServiceFee.objects.select_for_update().get(id=fee.id)
    if locked.status == PlatformServiceFee.Status.WAIVED:
        raise ValueError("This fee was waived and cannot be marked paid.")
    if locked.status != PlatformServiceFee.Status.PAID:
        locked.status = PlatformServiceFee.Status.PAID
        locked.save(update_fields=["status", "updated_at"])
        write_audit_log(
            actor_user=user,
            pharmacy=locked.pharmacy,
            action="billing.service_fee_paid",
            entity_type="PlatformServiceFee",
            entity_id=locked.id,
            summary=f"Marked service fee paid for {locked.pharmacy.name}",
        )
    return locked
