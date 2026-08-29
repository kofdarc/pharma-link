from __future__ import annotations

import logging
from decimal import Decimal

from django.db import transaction
from django.db.models import Avg, Count
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.audit.services import write_audit_log
from apps.billing.services import charge_platform_service_fee, waive_service_fee
from apps.common.mailer import send_email
from apps.customers.models import Client
from apps.insurance.services import cancel_claim_for_fulfillment
from apps.orders.models import Order, OrderFulfillment, PharmacyReview, StockReservation
from apps.orders.services.placement import release_reservations
from apps.payments.models import Payment
from apps.payments.services import refund_payment, settle_cash_on_delivery
from apps.sales.models import Sale
from apps.sales.services.create_sale import create_sale

logger = logging.getLogger(__name__)


class FulfillmentError(Exception):
    pass


def _notify_fulfillment_accepted(fulfillment: OrderFulfillment) -> None:
    order = fulfillment.order
    if not order.customer.email:
        return
    try:
        send_email(
            to=[order.customer.email],
            subject=f"{fulfillment.pharmacy.name} accepted your order {order.reference}",
            text_body=(
                f"Hi {order.contact_name},\n\n"
                f"{fulfillment.pharmacy.name} accepted its part of order {order.reference} and is preparing it now.\n"
            ),
        )
    except Exception:
        logger.exception("Failed to send fulfillment-accepted email for %s", order.reference)


def _notify_order_delivered(order: Order) -> None:
    verb = "is ready for collection" if order.status == Order.Status.COLLECTED else "has been delivered"
    if order.customer.email:
        try:
            send_email(
                to=[order.customer.email],
                subject=f"Order {order.reference} {verb}",
                text_body=f"Hi {order.contact_name},\n\nYour order {order.reference} {verb}. Thanks for shopping with HealthConnect.\n",
            )
        except Exception:
            logger.exception("Failed to send order-delivered email for %s", order.reference)
    from apps.messaging.notifications import notify_order_update

    detail = _("Your order is ready for collection.") if order.status == Order.Status.COLLECTED else _("Your order was delivered.")
    notify_order_update(order=order, event=order.status.lower(), detail=detail)


TERMINAL_FULFILLMENT_STATES = {
    OrderFulfillment.Status.DELIVERED,
    OrderFulfillment.Status.COLLECTED,
    OrderFulfillment.Status.REJECTED,
    OrderFulfillment.Status.CANCELLED,
}


def rollup_order_status(order: Order) -> str:
    """
    One order, many pharmacies: the shopper-facing status is the least advanced slice that
    still matters, so an order is only 'delivered' when every pharmacy's part arrived.
    """
    previous_status = order.status
    states = [fulfillment.status for fulfillment in order.fulfillments.all()]
    if not states:
        return order.status
    live = [
        state
        for state in states
        if state not in {OrderFulfillment.Status.REJECTED, OrderFulfillment.Status.CANCELLED, OrderFulfillment.Status.EXPIRED}
    ]
    if not live:
        order.status = Order.Status.CANCELLED
    elif all(state in {OrderFulfillment.Status.DELIVERED, OrderFulfillment.Status.COLLECTED} for state in live):
        delivered = Order.Status.COLLECTED if order.fulfillment_type == Order.FulfillmentType.PICKUP else Order.Status.DELIVERED
        order.status = Order.Status.PARTIALLY_CANCELLED if len(live) < len(states) else delivered
    elif any(state == OrderFulfillment.Status.PICKED_UP for state in live):
        order.status = Order.Status.IN_TRANSIT
    elif all(state == OrderFulfillment.Status.READY for state in live):
        order.status = Order.Status.READY
    elif any(state == OrderFulfillment.Status.ACCEPTED for state in live):
        order.status = Order.Status.CONFIRMED
    elif order.scheduled_for and order.released_at is None:
        order.status = Order.Status.SCHEDULED
    else:
        order.status = Order.Status.PENDING
    order.save(update_fields=["status", "updated_at"])
    if order.status in {Order.Status.DELIVERED, Order.Status.COLLECTED}:
        settle_cash_on_delivery(order=order)
        if previous_status != order.status:
            _notify_order_delivered(order)
    return order.status


@transaction.atomic
def accept_fulfillment(*, fulfillment: OrderFulfillment, user) -> OrderFulfillment:
    fulfillment = OrderFulfillment.objects.select_for_update().get(id=fulfillment.id)
    if fulfillment.status != OrderFulfillment.Status.PENDING:
        raise FulfillmentError(_("Only a pending order slice can be accepted."))
    hold_expired = StockReservation.objects.filter(
        order_line__fulfillment=fulfillment, released_at__isnull=True, consumed_at__isnull=True, expires_at__lt=timezone.now()
    ).exists()
    if hold_expired:
        raise FulfillmentError(_("The stock hold for this order has expired and can no longer be accepted."))
    fulfillment.status = OrderFulfillment.Status.ACCEPTED
    fulfillment.accepted_at = timezone.now()
    fulfillment.save(update_fields=["status", "accepted_at", "updated_at"])
    charge_platform_service_fee(fulfillment=fulfillment)
    rollup_order_status(fulfillment.order)
    write_audit_log(
        actor_user=user,
        pharmacy=fulfillment.pharmacy,
        action="orders.fulfillment_accepted",
        entity_type="OrderFulfillment",
        entity_id=fulfillment.id,
        summary=f"Accepted {fulfillment.order.reference}",
    )
    _notify_fulfillment_accepted(fulfillment)
    from apps.messaging.notifications import notify_order_update

    notify_order_update(
        order=fulfillment.order,
        pharmacy=fulfillment.pharmacy,
        event="accepted",
        detail=_("%(pharmacy)s accepted its part of your order.") % {"pharmacy": fulfillment.pharmacy.name},
    )
    return fulfillment


@transaction.atomic
def reject_fulfillment(*, fulfillment: OrderFulfillment, user, reason: str = "") -> OrderFulfillment:
    fulfillment = OrderFulfillment.objects.select_for_update().get(id=fulfillment.id)
    if fulfillment.status in TERMINAL_FULFILLMENT_STATES:
        raise FulfillmentError(_("This order slice is already closed."))
    release_reservations(fulfillment=fulfillment)
    waive_service_fee(fulfillment=fulfillment, reason=reason, user=user)
    cancel_claim_for_fulfillment(fulfillment=fulfillment, user=user, reason=reason)
    fulfillment.status = OrderFulfillment.Status.REJECTED
    fulfillment.rejection_reason = reason
    fulfillment.completed_at = timezone.now()
    fulfillment.save(update_fields=["status", "rejection_reason", "completed_at", "updated_at"])

    pharmacy = fulfillment.pharmacy
    pharmacy.orders_rejected += 1
    pharmacy.save(update_fields=["orders_rejected", "updated_at"])
    recompute_reliability(pharmacy)

    order = fulfillment.order
    order.items_subtotal = sum(
        (slice_.subtotal for slice_ in order.fulfillments.exclude(status__in=[OrderFulfillment.Status.REJECTED, OrderFulfillment.Status.CANCELLED])),
        Decimal("0"),
    )
    order.total = order.items_subtotal + order.delivery_fee
    order.save(update_fields=["items_subtotal", "total", "updated_at"])
    rollup_order_status(order)
    write_audit_log(
        actor_user=user,
        pharmacy=pharmacy,
        action="orders.fulfillment_rejected",
        entity_type="OrderFulfillment",
        entity_id=fulfillment.id,
        summary=f"Rejected {order.reference}: {reason}",
    )
    from apps.messaging.notifications import notify_order_update

    notify_order_update(
        order=order,
        pharmacy=pharmacy,
        event="rejected",
        detail=_("%(pharmacy)s could not fulfill its part. Review the updated order.") % {"pharmacy": pharmacy.name},
    )
    return fulfillment


@transaction.atomic
def mark_ready(*, fulfillment: OrderFulfillment, user) -> OrderFulfillment:
    fulfillment = OrderFulfillment.objects.select_for_update().get(id=fulfillment.id)
    if fulfillment.status != OrderFulfillment.Status.ACCEPTED:
        raise FulfillmentError(_("Accept the order before marking it ready."))
    fulfillment.status = OrderFulfillment.Status.READY
    fulfillment.ready_at = timezone.now()
    fulfillment.save(update_fields=["status", "ready_at", "updated_at"])
    rollup_order_status(fulfillment.order)
    from apps.messaging.notifications import notify_order_update

    notify_order_update(
        order=fulfillment.order,
        pharmacy=fulfillment.pharmacy,
        event="ready",
        detail=_("%(pharmacy)s prepared its part of your order.") % {"pharmacy": fulfillment.pharmacy.name},
    )
    return fulfillment


@transaction.atomic
def hand_over(*, fulfillment: OrderFulfillment, user, handover_code: str = "", collected_in_store: bool = False) -> OrderFulfillment:
    """
    Stock leaves the pharmacy here, and only here: the held units are consumed and a real
    invoice is written, so an online order lands in the pharmacy's books like a counter sale.
    """
    fulfillment = OrderFulfillment.objects.select_for_update().get(id=fulfillment.id)
    if fulfillment.status not in {OrderFulfillment.Status.ACCEPTED, OrderFulfillment.Status.READY}:
        raise FulfillmentError(_("This order slice is not ready for handover."))
    if handover_code and handover_code.strip() != fulfillment.handover_code:
        raise FulfillmentError(_("Handover code does not match."))

    release_reservations(fulfillment=fulfillment, consume=True)
    order = fulfillment.order
    client = Client.objects.filter(pharmacy=fulfillment.pharmacy, platform_user=order.customer).first()
    sale = create_sale(
        user=user,
        pharmacy=fulfillment.pharmacy,
        items=[{"medicine": line.medicine_id, "quantity": line.quantity, "unit_price": line.unit_price} for line in fulfillment.lines.all()],
        payment_method=Sale.PaymentMethod.OTHER,
        notes=f"Platform order {order.reference}",
        client=client,
        channel=Sale.Channel.PLATFORM_ORDER,
        # Cover for any prescription-only line. Placement already checked that
        # this prescription is consumable and covers the basket, so the sale
        # must not ask the pharmacy for a second one at the counter.
        eprescription=order.prescription,
    )
    fulfillment.sale = sale
    fulfillment.status = OrderFulfillment.Status.COLLECTED if collected_in_store else OrderFulfillment.Status.PICKED_UP
    fulfillment.picked_up_at = timezone.now()
    if collected_in_store:
        fulfillment.completed_at = fulfillment.picked_up_at
    fulfillment.save(update_fields=["sale", "status", "picked_up_at", "completed_at", "updated_at"])

    pharmacy = fulfillment.pharmacy
    pharmacy.orders_fulfilled += 1
    pharmacy.save(update_fields=["orders_fulfilled", "updated_at"])
    recompute_reliability(pharmacy)
    rollup_order_status(order)
    return fulfillment


@transaction.atomic
def mark_delivered(*, fulfillment: OrderFulfillment) -> OrderFulfillment:
    fulfillment = OrderFulfillment.objects.select_for_update().get(id=fulfillment.id)
    if fulfillment.status != OrderFulfillment.Status.PICKED_UP:
        raise FulfillmentError(_("Only a picked-up order slice can be delivered."))
    fulfillment.status = OrderFulfillment.Status.DELIVERED
    fulfillment.completed_at = timezone.now()
    fulfillment.save(update_fields=["status", "completed_at", "updated_at"])
    rollup_order_status(fulfillment.order)
    return fulfillment


@transaction.atomic
def cancel_order(*, order: Order, user, reason: str = "") -> Order:
    order = Order.objects.select_for_update().get(id=order.id)
    if order.status in {Order.Status.DELIVERED, Order.Status.COLLECTED, Order.Status.CANCELLED}:
        raise FulfillmentError(_("This order is already closed."))
    for fulfillment in order.fulfillments.select_for_update():
        if fulfillment.status in {OrderFulfillment.Status.PICKED_UP, OrderFulfillment.Status.DELIVERED, OrderFulfillment.Status.COLLECTED}:
            raise FulfillmentError(_("Part of this order already left the pharmacy. Contact support instead."))
        release_reservations(fulfillment=fulfillment)
        cancel_claim_for_fulfillment(fulfillment=fulfillment, user=user, reason=reason)
        fulfillment.status = OrderFulfillment.Status.CANCELLED
        fulfillment.completed_at = timezone.now()
        fulfillment.save(update_fields=["status", "completed_at", "updated_at"])
    order.status = Order.Status.CANCELLED
    order.cancelled_reason = reason
    order.save(update_fields=["status", "cancelled_reason", "updated_at"])
    payment = getattr(order, "payment", None)
    if payment is not None and payment.status == Payment.Status.PAID:
        refund_payment(payment=payment, user=user)
    write_audit_log(
        actor_user=user,
        action="orders.cancelled",
        entity_type="Order",
        entity_id=order.id,
        summary=f"Cancelled {order.reference}: {reason}",
    )
    return order


def recompute_reliability(pharmacy) -> None:
    total = pharmacy.orders_fulfilled + pharmacy.orders_rejected
    pharmacy.fulfillment_success_rate = Decimal("100") if total == 0 else (Decimal(pharmacy.orders_fulfilled) * 100 / Decimal(total)).quantize(Decimal("0.01"))
    pharmacy.save(update_fields=["fulfillment_success_rate", "updated_at"])


@transaction.atomic
def submit_review(*, order: Order, pharmacy, customer, rating: int, comment: str = "", was_complete: bool = True) -> PharmacyReview:
    if order.customer_id != customer.id:
        raise FulfillmentError(_("You can only review your own orders."))
    if order.status not in {Order.Status.DELIVERED, Order.Status.COLLECTED, Order.Status.PARTIALLY_CANCELLED}:
        raise FulfillmentError(_("Review an order once it has been delivered."))
    if not order.fulfillments.filter(pharmacy=pharmacy).exists():
        raise FulfillmentError(_("That pharmacy was not part of this order."))

    review, created = PharmacyReview.objects.update_or_create(
        order=order,
        pharmacy=pharmacy,
        defaults={"customer": customer, "rating": rating, "comment": comment, "was_complete": was_complete},
    )
    recompute_rating(pharmacy)
    write_audit_log(
        actor_user=customer,
        pharmacy=pharmacy,
        action="orders.review_submitted" if created else "orders.review_edited",
        entity_type="PharmacyReview",
        entity_id=review.id,
        summary=f"{'Reviewed' if created else 'Edited review for'} {order.reference}: {rating}/5",
        after_data={"rating": rating, "was_complete": was_complete},
    )
    return review


def recompute_rating(pharmacy) -> None:
    aggregate = PharmacyReview.objects.filter(pharmacy=pharmacy, is_hidden=False).aggregate(average=Avg("rating"), count=Count("id"))
    pharmacy.rating_average = Decimal(str(round(aggregate["average"] or 0, 2)))
    pharmacy.rating_count = aggregate["count"] or 0
    pharmacy.save(update_fields=["rating_average", "rating_count", "updated_at"])


@transaction.atomic
def set_review_visibility(*, review: PharmacyReview, is_hidden: bool, reason: str = "", user=None) -> PharmacyReview:
    review.is_hidden = is_hidden
    review.hidden_reason = reason if is_hidden else ""
    review.save(update_fields=["is_hidden", "hidden_reason", "updated_at"])
    recompute_rating(review.pharmacy)
    write_audit_log(
        actor_user=user,
        pharmacy=review.pharmacy,
        action="orders.review_hidden" if is_hidden else "orders.review_unhidden",
        entity_type="PharmacyReview",
        entity_id=review.id,
        summary=f"{'Hid' if is_hidden else 'Unhid'} review on {review.order.reference}" + (f": {reason}" if reason else ""),
    )
    return review
