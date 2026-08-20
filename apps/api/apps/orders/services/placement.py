from __future__ import annotations

import logging
import secrets
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.audit.services import write_audit_log
from apps.common.mailer import send_email
from apps.customers.services import link_or_create_client_for_shopper
from apps.inventory.models import InventoryBatch
from apps.medicines.models import Medicine
from apps.orders.models import (
    DeliveryAddress,
    Order,
    OrderFulfillment,
    OrderLine,
    StockReservation,
    UnmetDemandSignal,
)
from apps.orders.services.sourcing import plan_basket
from apps.payments.models import Payment
from apps.payments.services import create_payment_for_order
from apps.pharmacies.models import Pharmacy

logger = logging.getLogger(__name__)


class OrderError(Exception):
    pass


def _notify_order_placed(order: Order) -> None:
    if not order.customer.email:
        return
    try:
        send_email(
            to=[order.customer.email],
            subject=_("Order %(reference)s placed") % {"reference": order.reference},
            text_body=_(
                "Hi %(name)s,\n\n"
                "We've received your order %(reference)s totalling %(total)s %(currency)s. "
                "We'll email you again as soon as a pharmacy accepts it.\n"
            )
            % {"name": order.contact_name, "reference": order.reference, "total": order.total, "currency": settings.PLATFORM_CURRENCY},
        )
    except Exception:
        logger.exception("Failed to send order-placed email for %s", order.reference)


def _notify_webhooks_order_placed(order: Order) -> None:
    from apps.integrations.services.webhooks import dispatch_webhook_event

    for fulfillment in order.fulfillments.select_related("pharmacy"):
        try:
            dispatch_webhook_event(
                pharmacy=fulfillment.pharmacy,
                event_type="order.placed",
                payload={
                    "order_reference": order.reference,
                    "fulfillment_id": str(fulfillment.id),
                    "pharmacy": fulfillment.pharmacy.name,
                    "subtotal": str(fulfillment.subtotal),
                    "fulfillment_type": order.fulfillment_type,
                    "items": [
                        {"medicine": str(line.medicine), "quantity": line.quantity}
                        for line in fulfillment.lines.select_related("medicine")
                    ],
                },
            )
        except Exception:
            logger.exception("Failed to dispatch order.placed webhook for %s @ %s", order.reference, fulfillment.pharmacy_id)


def next_reference() -> str:
    stamp = timezone.now().strftime("%y%m%d")
    return f"MO-{stamp}-{secrets.randbelow(100000):05d}"


def _check_prescription_requirements(*, items: list[dict], medicines_by_id: dict, prescription) -> None:
    """
    An item flagged requires_prescription must be covered by a currently-consumable
    e-prescription with enough remaining quantity on a matching line. Basket sourcing has
    no other concept of a prescription, so this is the enforcement point for online orders.
    """
    needed = {}
    for entry in items:
        medicine_id = str(entry["medicine"])
        medicine = medicines_by_id.get(medicine_id)
        if medicine is not None and medicine.requires_prescription:
            needed[medicine_id] = entry
    if not needed:
        return
    if prescription is None or not prescription.is_consumable:
        names = ", ".join(str(medicines_by_id[medicine_id]) for medicine_id in needed)
        raise OrderError(_("A valid prescription is required to order: %(names)s.") % {"names": names})
    remaining_by_medicine: dict[str, int] = {}
    for item in prescription.items.all():
        if item.medicine_id:
            remaining_by_medicine[str(item.medicine_id)] = remaining_by_medicine.get(str(item.medicine_id), 0) + item.quantity_remaining
    for medicine_id, entry in needed.items():
        available = remaining_by_medicine.get(medicine_id, 0)
        if available < int(entry["quantity"]):
            raise OrderError(
                _("The prescription does not cover enough %(medicine)s for this order.") % {"medicine": medicines_by_id[medicine_id]}
            )


def _reserve_lines(*, pharmacy: Pharmacy, line: OrderLine, quantity: int, expires_at) -> None:
    """
    FEFO reservation across batches. Uses select_for_update so two shoppers cannot both
    claim the last box, and takes the earliest expiry first so the pharmacy's oldest
    stock always leaves first.
    """
    today = timezone.localdate()
    batches = list(
        InventoryBatch.objects.select_for_update()
        .filter(pharmacy=pharmacy, medicine=line.medicine, is_archived=False, current_quantity__gt=0)
        .exclude(expiry_date__lt=today)
        .order_by(F("expiry_date").asc(nulls_last=True), "created_at")
    )
    remaining = quantity
    for batch in batches:
        if remaining <= 0:
            break
        free = batch.available_quantity
        if free <= 0:
            continue
        take = min(free, remaining)
        StockReservation.objects.create(order_line=line, inventory_batch=batch, quantity=take, expires_at=expires_at)
        batch.reserved_quantity += take
        batch.save(update_fields=["reserved_quantity", "updated_at"])
        remaining -= take
    if remaining > 0:
        raise OrderError(
            _("%(medicine)s is no longer available in the requested quantity at %(pharmacy)s.")
            % {"medicine": line.medicine, "pharmacy": pharmacy.name}
        )


def place_order(
    *,
    customer,
    items: list[dict],
    address: DeliveryAddress | None = None,
    fulfillment_type: str = Order.FulfillmentType.DELIVERY,
    scheduled_for=None,
    window_minutes: int = 120,
    notes: str = "",
    prescription=None,
    source: str = Order.Source.WEB,
    recurring_order=None,
    payment_method: str = Payment.Provider.CASH_ON_DELIVERY,
    idempotency_key: str = "",
) -> Order:
    """
    Validates, sources, then persists.

    Sourcing is read-only and runs OUTSIDE the transaction on purpose: when a basket cannot
    be filled we record the unmet demand and raise, and a surrounding atomic block would
    roll that signal back - losing exactly the data pharmacies want. Only the writes below
    are transactional, and the reservation step re-checks stock under a row lock, so a
    basket that goes stale between planning and persisting fails safely.
    """
    if idempotency_key:
        existing = Order.objects.filter(customer=customer, idempotency_key=idempotency_key).first()
        if existing is not None:
            return existing

    if fulfillment_type == Order.FulfillmentType.DELIVERY and address is None:
        raise OrderError(_("A delivery address is required."))
    if address is not None and address.user_id != customer.id:
        raise OrderError(_("That address belongs to another account."))

    cap = settings.PUBLIC_MAX_QUANTITY_PER_ITEM
    medicines_by_id = {}
    for entry in items:
        medicine = Medicine.objects.filter(id=entry["medicine"]).first()
        medicines_by_id[str(entry["medicine"])] = medicine
        if int(entry["quantity"]) > cap:
            raise OrderError(
                _("Online orders are limited to %(cap)s units of %(medicine)s at a time.")
                % {"cap": cap, "medicine": medicine or _("an item")}
            )

    _check_prescription_requirements(items=items, medicines_by_id=medicines_by_id, prescription=prescription)

    latitude = float(address.latitude) if address else None
    longitude = float(address.longitude) if address else None
    if latitude is None:
        raise OrderError(_("A geocoded address is required to source a basket."))

    if scheduled_for and scheduled_for <= timezone.now():
        raise OrderError(_("Pick a time in the future for a scheduled order."))
    if scheduled_for and scheduled_for > timezone.now() + timedelta(days=settings.MAX_ORDER_SCHEDULE_DAYS):
        raise OrderError(_("Orders can be scheduled up to %(days)s days ahead.") % {"days": settings.MAX_ORDER_SCHEDULE_DAYS})

    plan = plan_basket(items=items, latitude=latitude, longitude=longitude)
    if not plan["allocations"]:
        _record_unmet(items, address.area if address else "")
        raise OrderError(_("No pharmacy near you can supply these items right now."))

    order = _persist_order(
        customer=customer,
        plan=plan,
        address=address,
        fulfillment_type=fulfillment_type,
        scheduled_for=scheduled_for,
        window_minutes=window_minutes,
        notes=notes,
        prescription=prescription,
        source=source,
        recurring_order=recurring_order,
        payment_method=payment_method,
        idempotency_key=idempotency_key,
    )

    if plan["unfulfilled"]:
        _record_unmet([{"medicine": row["medicine"], "quantity": row["quantity_short"]} for row in plan["unfulfilled"]], order.area)

    write_audit_log(
        actor_user=customer,
        action="orders.placed",
        entity_type="Order",
        entity_id=order.id,
        summary=f"Order {order.reference} across {len(plan['allocations'])} pharmacy(ies)",
        after_data={"total": str(order.total), "pharmacies": len(plan["allocations"]), "scheduled_for": scheduled_for.isoformat() if scheduled_for else None},
    )
    _notify_order_placed(order)
    _notify_webhooks_order_placed(order)
    return order


@transaction.atomic
def _persist_order(
    *,
    customer,
    plan: dict,
    address: DeliveryAddress | None,
    fulfillment_type: str,
    scheduled_for,
    window_minutes: int,
    notes: str,
    prescription,
    source: str,
    recurring_order,
    payment_method: str,
    idempotency_key: str = "",
) -> Order:
    order = Order.objects.create(
        reference=next_reference(),
        customer=customer,
        idempotency_key=idempotency_key,
        fulfillment_type=fulfillment_type,
        status=Order.Status.SCHEDULED if scheduled_for else Order.Status.PENDING,
        source=source,
        recurring_order=recurring_order,
        prescription=prescription,
        contact_name=address.contact_name if address else (customer.get_full_name() or customer.email),
        contact_phone=address.phone if address else "",
        address=address.address if address else "",
        area=address.area if address else "",
        city=address.city if address else "",
        latitude=address.latitude if address else None,
        longitude=address.longitude if address else None,
        delivery_notes=address.building_notes if address else "",
        scheduled_for=scheduled_for,
        window_minutes=window_minutes,
        released_at=None if scheduled_for else timezone.now(),
        notes=notes,
    )

    # A scheduled order holds stock only from its release window, not for days on end.
    hold_until = (scheduled_for or timezone.now()) + timedelta(minutes=settings.STOCK_RESERVATION_MINUTES)

    subtotal = Decimal("0")
    for allocation in plan["allocations"]:
        pharmacy = Pharmacy.objects.get(id=allocation["pharmacy"])
        fulfillment = OrderFulfillment.objects.create(
            order=order,
            pharmacy=pharmacy,
            subtotal=allocation["subtotal"],
            handover_code=f"{secrets.randbelow(1000000):06d}",
        )
        for raw_line in allocation["lines"]:
            medicine = Medicine.objects.get(id=raw_line["medicine"])
            line = OrderLine.objects.create(
                fulfillment=fulfillment,
                medicine=medicine,
                quantity=raw_line["quantity"],
                unit_price=raw_line["unit_price"],
                line_total=raw_line["line_total"],
                is_price_regulated=raw_line["is_price_regulated"],
            )
            _reserve_lines(pharmacy=pharmacy, line=line, quantity=line.quantity, expires_at=hold_until)
        subtotal += allocation["subtotal"]
        link_or_create_client_for_shopper(
            pharmacy=pharmacy,
            user=customer,
            contact_name=order.contact_name,
            phone=order.contact_phone,
            address=order.address,
            area=order.area,
        )

    delivery_fee = Decimal("0") if fulfillment_type == Order.FulfillmentType.PICKUP else Decimal(str(settings.DELIVERY_BASE_FEE))
    order.items_subtotal = subtotal
    order.delivery_fee = delivery_fee
    order.total = subtotal + delivery_fee
    order.save(update_fields=["items_subtotal", "delivery_fee", "total", "updated_at"])
    payment = create_payment_for_order(order=order, provider_code=payment_method, user=customer)
    if payment.status == Payment.Status.FAILED:
        raise OrderError(_("Payment failed: %(reason)s") % {"reason": payment.failure_reason or _("the charge was declined.")})
    return order


def _record_unmet(items: list[dict], area: str) -> None:
    for entry in items:
        UnmetDemandSignal.objects.create(
            medicine_id=entry.get("medicine"),
            area=area,
            quantity_requested=int(entry.get("quantity", 1)),
            source=UnmetDemandSignal.Source.BASKET,
        )


@transaction.atomic
def release_reservations(*, fulfillment: OrderFulfillment, consume: bool = False) -> None:
    """Give held units back to the shelf, or mark them consumed once a sale has deducted them."""
    now = timezone.now()
    reservations = StockReservation.objects.select_for_update().filter(
        order_line__fulfillment=fulfillment, released_at__isnull=True, consumed_at__isnull=True
    )
    for reservation in reservations:
        batch = InventoryBatch.objects.select_for_update().get(id=reservation.inventory_batch_id)
        batch.reserved_quantity = max(0, batch.reserved_quantity - reservation.quantity)
        batch.save(update_fields=["reserved_quantity", "updated_at"])
        if consume:
            reservation.consumed_at = now
            reservation.save(update_fields=["consumed_at", "updated_at"])
        else:
            reservation.released_at = now
            reservation.save(update_fields=["released_at", "updated_at"])


@transaction.atomic
def expire_stale_reservations(*, now=None) -> int:
    """
    Housekeeping: an order nobody accepted must not keep stock off the shelf forever. A
    fulfillment still PENDING when its hold expires is moved to EXPIRED so the order stops
    sitting invisible in limbo - see accept_fulfillment's stock re-check for the case where
    a pharmacy tries to accept after the hold already lapsed.
    """
    from apps.orders.services.lifecycle import rollup_order_status

    now = now or timezone.now()
    stale = (
        StockReservation.objects.select_for_update()
        .filter(released_at__isnull=True, consumed_at__isnull=True, expires_at__lt=now)
        .select_related("order_line__fulfillment__order")
    )
    released = 0
    expired_fulfillment_ids = set()
    for reservation in stale:
        fulfillment = reservation.order_line.fulfillment
        if fulfillment.status in {OrderFulfillment.Status.PICKED_UP, OrderFulfillment.Status.DELIVERED, OrderFulfillment.Status.COLLECTED}:
            continue
        batch = InventoryBatch.objects.select_for_update().get(id=reservation.inventory_batch_id)
        batch.reserved_quantity = max(0, batch.reserved_quantity - reservation.quantity)
        batch.save(update_fields=["reserved_quantity", "updated_at"])
        reservation.released_at = now
        reservation.save(update_fields=["released_at", "updated_at"])
        released += 1
        if fulfillment.status == OrderFulfillment.Status.PENDING:
            expired_fulfillment_ids.add(fulfillment.id)

    for fulfillment_id in expired_fulfillment_ids:
        fulfillment = OrderFulfillment.objects.select_for_update().select_related("order").get(id=fulfillment_id)
        if fulfillment.status != OrderFulfillment.Status.PENDING:
            continue
        fulfillment.status = OrderFulfillment.Status.EXPIRED
        fulfillment.completed_at = now
        fulfillment.save(update_fields=["status", "completed_at", "updated_at"])
        order = fulfillment.order
        order.items_subtotal = sum(
            (slice_.subtotal for slice_ in order.fulfillments.exclude(
                status__in=[OrderFulfillment.Status.REJECTED, OrderFulfillment.Status.CANCELLED, OrderFulfillment.Status.EXPIRED]
            )),
            Decimal("0"),
        )
        order.total = order.items_subtotal + order.delivery_fee
        order.save(update_fields=["items_subtotal", "total", "updated_at"])
        rollup_order_status(order)
        write_audit_log(
            action="orders.fulfillment_expired",
            entity_type="OrderFulfillment",
            entity_id=fulfillment.id,
            summary=f"Stock hold expired before {fulfillment.pharmacy.name} accepted {order.reference}",
        )
    return released
