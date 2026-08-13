from __future__ import annotations

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
