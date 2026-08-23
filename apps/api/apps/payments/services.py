from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.audit.services import write_audit_log
from apps.common.mailer import send_email
from apps.payments.models import Payment
from apps.payments.providers.registry import get_provider

logger = logging.getLogger(__name__)


class PaymentError(Exception):
    pass


def _notify_payment_failed(payment: Payment) -> None:
    customer = payment.order.customer
    if not customer.email:
        return
    try:
        send_email(
            to=[customer.email],
            subject=_("Payment failed for order %(reference)s") % {"reference": payment.order.reference},
            text_body=_("Hi %(name)s,\n\nYour payment for order %(reference)s could not be processed%(reason)s\n")
            % {
                "name": payment.order.contact_name,
                "reference": payment.order.reference,
                "reason": _(": %(reason)s") % {"reason": payment.failure_reason} if payment.failure_reason else ".",
            },
        )
    except Exception:
        logger.exception("Failed to send payment-failed email for %s", payment.order.reference)


@transaction.atomic
def create_payment_for_order(*, order, provider_code: str, user=None, amount=None) -> Payment:
    """
    `amount` defaults to the order's full total. Insured checkouts pass an explicit
    lower amount - what the shopper actually owes after insurance covers its share - so
    the payment charged matches the patient's copay rather than the order's list price.
    """
    if hasattr(order, "payment"):
        raise PaymentError(_("This order already has a payment on file."))
    payment = Payment.objects.create(order=order, provider=provider_code, amount=amount if amount is not None else order.total, status=Payment.Status.PENDING)
    if provider_code == Payment.Provider.CASH_ON_DELIVERY:
        return payment
    return charge_payment(payment=payment, user=user)


@transaction.atomic
def charge_payment(*, payment: Payment, user=None) -> Payment:
    """
    Mutates and returns the SAME `payment` instance the caller passed in, rather than a
    freshly-fetched copy - `order.payment` is a cached reverse accessor, so a detached copy
    would leave that cache (and anything already holding it, like the order API response)
    silently pointing at the pre-charge PENDING state.
    """
    locked = Payment.objects.select_for_update().get(id=payment.id)
    if locked.status != Payment.Status.PAID:
        provider = get_provider(locked.provider)
        result = provider.charge(locked)
        locked.status = result.status
        locked.external_reference = result.external_reference or locked.external_reference
        locked.raw_response = result.raw
        locked.failure_reason = result.failure_reason
        locked.paid_at = timezone.now() if result.status == Payment.Status.PAID else locked.paid_at
        locked.save(update_fields=["status", "external_reference", "raw_response", "failure_reason", "paid_at", "updated_at"])
        write_audit_log(
            actor_user=user,
            action="payments.charged" if result.status == Payment.Status.PAID else "payments.charge_failed",
            entity_type="Payment",
            entity_id=locked.id,
            summary=f"{locked.provider} charge for {locked.order.reference}: {locked.status}",
            after_data={"amount": str(locked.amount), "status": locked.status},
        )
        if result.status == Payment.Status.FAILED:
            _notify_payment_failed(locked)
    for field in ("status", "external_reference", "raw_response", "failure_reason", "paid_at"):
        setattr(payment, field, getattr(locked, field))
    return payment


@transaction.atomic
def refund_payment(*, payment: Payment, user=None) -> Payment:
    """
    Mirrors charge_payment: locks, delegates to the adapter, mutates the caller's instance in
    place. A payment that was never actually charged (PENDING, e.g. cash on delivery
    cancelled before handover) has nothing to reverse and is left alone. Already-refunded or
    failed payments are a no-op, so cancelling twice cannot double-refund.
    """
    locked = Payment.objects.select_for_update().get(id=payment.id)
    if locked.status == Payment.Status.PAID:
        provider = get_provider(locked.provider)
        result = provider.refund(locked)
        locked.status = result.status
        locked.external_reference = result.external_reference or locked.external_reference
        locked.raw_response = result.raw
        locked.save(update_fields=["status", "external_reference", "raw_response", "updated_at"])
        write_audit_log(
            actor_user=user,
            action="payments.refunded",
            entity_type="Payment",
            entity_id=locked.id,
            summary=f"{locked.provider} refund for {locked.order.reference}",
            after_data={"amount": str(locked.amount), "status": locked.status},
        )
    for field in ("status", "external_reference", "raw_response", "failure_reason", "paid_at"):
        setattr(payment, field, getattr(locked, field))
    return payment


@transaction.atomic
def settle_cash_on_delivery(*, order) -> None:
    """Once an order is fully delivered/collected the COD cash has actually changed hands,
    so its payment can move from PENDING to PAID. No-op for any other provider or state."""
    payment = getattr(order, "payment", None)
    if payment is None or payment.provider != Payment.Provider.CASH_ON_DELIVERY or payment.status != Payment.Status.PENDING:
        return
    payment.status = Payment.Status.PAID
    payment.paid_at = timezone.now()
    payment.save(update_fields=["status", "paid_at", "updated_at"])
