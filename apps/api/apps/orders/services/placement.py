from __future__ import annotations

import secrets
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.audit.services import write_audit_log
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


class OrderError(Exception):
    pass


def next_reference() -> str:
    stamp = timezone.now().strftime("%y%m%d")
    return f"MO-{stamp}-{secrets.randbelow(100000):05d}"


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
        raise OrderError(f"{line.medicine} is no longer available in the requested quantity at {pharmacy.name}.")


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
) -> Order:
    """
    Validates, sources, then persists.

    Sourcing is read-only and runs OUTSIDE the transaction on purpose: when a basket cannot
    be filled we record the unmet demand and raise, and a surrounding atomic block would
    roll that signal back - losing exactly the data pharmacies want. Only the writes below
    are transactional, and the reservation step re-checks stock under a row lock, so a
    basket that goes stale between planning and persisting fails safely.
    """
    if fulfillment_type == Order.FulfillmentType.DELIVERY and address is None:
        raise OrderError("A delivery address is required.")
    if address is not None and address.user_id != customer.id:
        raise OrderError("That address belongs to another account.")

    cap = settings.PUBLIC_MAX_QUANTITY_PER_ITEM
    for entry in items:
        if int(entry["quantity"]) > cap:
            medicine = Medicine.objects.filter(id=entry["medicine"]).first()
            raise OrderError(f"Online orders are limited to {cap} units of {medicine or 'an item'} at a time.")

    latitude = float(address.latitude) if address else None
    longitude = float(address.longitude) if address else None
    if latitude is None:
        raise OrderError("A geocoded address is required to source a basket.")

    if scheduled_for and scheduled_for <= timezone.now():
        raise OrderError("Pick a time in the future for a scheduled order.")
    if scheduled_for and scheduled_for > timezone.now() + timedelta(days=settings.MAX_ORDER_SCHEDULE_DAYS):
        raise OrderError(f"Orders can be scheduled up to {settings.MAX_ORDER_SCHEDULE_DAYS} days ahead.")

    plan = plan_basket(items=items, latitude=latitude, longitude=longitude)
    if not plan["allocations"]:
        _record_unmet(items, address.area if address else "")
        raise OrderError("No pharmacy near you can supply these items right now.")

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
) -> Order:
    order = Order.objects.create(
        reference=next_reference(),
        customer=customer,
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
    create_payment_for_order(order=order, provider_code=payment_method, user=customer)
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
    """Housekeeping: an order nobody accepted must not keep stock off the shelf forever."""
    now = now or timezone.now()
    stale = (
        StockReservation.objects.select_for_update()
        .filter(released_at__isnull=True, consumed_at__isnull=True, expires_at__lt=now)
        .select_related("order_line__fulfillment__order")
    )
    released = 0
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
    return released
