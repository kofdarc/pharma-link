from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.common.mailer import send_email
from apps.delivery.models import DeliveryRoute, Driver, DriverLocationPing, RouteEvent, RouteStop
from apps.orders.models import Order, OrderFulfillment
from apps.orders.services.lifecycle import hand_over, mark_delivered

logger = logging.getLogger(__name__)


class OperationError(Exception):
    pass


def _notify_driver_assigned(*, order: Order, driver: Driver) -> None:
    if not order.customer.email:
        return
    try:
        send_email(
            to=[order.customer.email],
            subject=_("A driver is on the way for order %(reference)s") % {"reference": order.reference},
            text_body=_("Hi %(name)s,\n\n%(driver)s has been assigned to deliver your order %(reference)s.\n")
            % {"name": order.contact_name, "driver": driver.full_name, "reference": order.reference},
        )
    except Exception:
        logger.exception("Failed to send driver-assigned email for %s", order.reference)


@transaction.atomic
def accept_route(*, route: DeliveryRoute, driver: Driver) -> DeliveryRoute:
    route = DeliveryRoute.objects.select_for_update().get(id=route.id)
    if route.driver_id != driver.id:
        raise OperationError(_("This route was planned for another driver."))
    if route.status not in {DeliveryRoute.Status.PROPOSED, DeliveryRoute.Status.OFFERED}:
        raise OperationError(_("This route can no longer be accepted."))
    if driver.routes.filter(status=DeliveryRoute.Status.ACTIVE).exists():
        raise OperationError(_("Finish your active route first."))
    route.status = DeliveryRoute.Status.ACTIVE
    route.accepted_at = timezone.now()
    route.started_at = route.accepted_at
    route.save(update_fields=["status", "accepted_at", "started_at", "updated_at"])

    OrderFulfillment.objects.filter(route_tasks__stop__route=route).distinct().update(updated_at=timezone.now())
    RouteEvent.objects.create(route=route, event="accepted", detail=f"{driver.full_name} accepted the route", actor_user=driver.user)

    orders = Order.objects.filter(route_stops__route=route, route_stops__kind=RouteStop.Kind.DROPOFF).distinct().select_related("customer")
    for order in orders:
        _notify_driver_assigned(order=order, driver=driver)

    return route


@transaction.atomic
def arrive_at_stop(*, stop: RouteStop, driver: Driver) -> RouteStop:
    stop = RouteStop.objects.select_for_update().get(id=stop.id)
    if stop.route.driver_id != driver.id:
        raise OperationError(_("This stop is not on your route."))
    if stop.route.status != DeliveryRoute.Status.ACTIVE:
        raise OperationError(_("Accept the route before starting it."))
    if stop.status != RouteStop.Status.PENDING:
        raise OperationError(_("This stop is not pending."))
    stop.status = RouteStop.Status.ARRIVED
    stop.arrived_at = timezone.now()
    stop.save(update_fields=["status", "arrived_at", "updated_at"])
    RouteEvent.objects.create(route=stop.route, stop=stop, event="arrived", detail=stop.label, actor_user=driver.user)
    return stop


@transaction.atomic
def complete_pickup(*, stop: RouteStop, driver: Driver, handover_codes: dict[str, str] | None = None) -> RouteStop:
    """
    Collects everything owed at this pharmacy - possibly for several different customers.
    Each fulfillment is handed over against its own code, which is also what writes the
    pharmacy's invoice and finally decrements stock.
    """
    stop = RouteStop.objects.select_for_update().get(id=stop.id)
    if stop.route.driver_id != driver.id:
        raise OperationError(_("This stop is not on your route."))
    if stop.kind != RouteStop.Kind.PICKUP:
        raise OperationError(_("This stop is not a pickup."))
    if stop.status not in {RouteStop.Status.PENDING, RouteStop.Status.ARRIVED}:
        raise OperationError(_("This stop is already closed."))

    handover_codes = handover_codes or {}
    for task in stop.tasks.select_related("order_fulfillment"):
        fulfillment = task.order_fulfillment
        if fulfillment.status in {OrderFulfillment.Status.PICKED_UP, OrderFulfillment.Status.DELIVERED}:
            task.is_done = True
            task.save(update_fields=["is_done", "updated_at"])
            continue
        code = handover_codes.get(str(fulfillment.id), "")
        hand_over(fulfillment=fulfillment, user=driver.user, handover_code=code)
        task.is_done = True
        task.save(update_fields=["is_done", "updated_at"])

    stop.status = RouteStop.Status.DONE
    stop.completed_at = timezone.now()
    stop.save(update_fields=["status", "completed_at", "updated_at"])
    RouteEvent.objects.create(
        route=stop.route,
        stop=stop,
        event="picked_up",
        detail=f"{stop.label}: {stop.tasks.count()} order(s) collected in one visit",
        actor_user=driver.user,
    )
    _close_route_if_done(stop.route)
    return stop


@transaction.atomic
def complete_dropoff(*, stop: RouteStop, driver: Driver, recipient_note: str = "") -> RouteStop:
    stop = RouteStop.objects.select_for_update().get(id=stop.id)
    if stop.route.driver_id != driver.id:
        raise OperationError(_("This stop is not on your route."))
    if stop.kind != RouteStop.Kind.DROPOFF:
        raise OperationError(_("This stop is not a delivery."))
    if stop.status not in {RouteStop.Status.PENDING, RouteStop.Status.ARRIVED}:
        raise OperationError(_("This stop is already closed."))

    for task in stop.tasks.select_related("order_fulfillment"):
        if task.order_fulfillment.status == OrderFulfillment.Status.PICKED_UP:
            mark_delivered(fulfillment=task.order_fulfillment)
        task.is_done = True
        task.save(update_fields=["is_done", "updated_at"])

    stop.status = RouteStop.Status.DONE
    stop.completed_at = timezone.now()
    stop.save(update_fields=["status", "completed_at", "updated_at"])
    RouteEvent.objects.create(route=stop.route, stop=stop, event="delivered", detail=f"{stop.label} {recipient_note}".strip(), actor_user=driver.user)
    _close_route_if_done(stop.route)
    return stop


@transaction.atomic
def fail_stop(*, stop: RouteStop, driver: Driver, reason: str) -> RouteStop:
    """
    A stop a driver could not complete (pharmacy closed, recipient unreachable, ...). The
    order slices riding on this stop must not sit invisibly in whatever status they were in -
    they move to DELIVERY_FAILED so an admin sees them on the dispatch board and can
    re-dispatch or otherwise resolve them by hand.
    """
    from apps.audit.services import write_audit_log
    from apps.orders.services.lifecycle import rollup_order_status

    stop = RouteStop.objects.select_for_update().get(id=stop.id)
    if stop.route.driver_id != driver.id:
        raise OperationError(_("This stop is not on your route."))
    stop.status = RouteStop.Status.FAILED
    stop.failure_reason = reason[:255]
    stop.completed_at = timezone.now()
    stop.save(update_fields=["status", "failure_reason", "completed_at", "updated_at"])
    RouteEvent.objects.create(route=stop.route, stop=stop, event="failed", detail=reason[:255], actor_user=driver.user)

    closed_statuses = {OrderFulfillment.Status.DELIVERED, OrderFulfillment.Status.COLLECTED, OrderFulfillment.Status.REJECTED, OrderFulfillment.Status.CANCELLED}
    for task in stop.tasks.select_related("order_fulfillment__order", "order_fulfillment__pharmacy"):
        fulfillment = OrderFulfillment.objects.select_for_update().get(id=task.order_fulfillment_id)
        if fulfillment.status in closed_statuses:
            continue
        fulfillment.status = OrderFulfillment.Status.DELIVERY_FAILED
        fulfillment.completed_at = timezone.now()
        fulfillment.save(update_fields=["status", "completed_at", "updated_at"])
        write_audit_log(
            actor_user=driver.user,
            pharmacy=fulfillment.pharmacy,
            action="delivery.stop_failed",
            entity_type="OrderFulfillment",
            entity_id=fulfillment.id,
            summary=f"Delivery stop failed for {fulfillment.order.reference}: {reason[:255]}",
        )
        rollup_order_status(fulfillment.order)

    _close_route_if_done(stop.route)
    return stop


def _close_route_if_done(route: DeliveryRoute) -> None:
    if route.stops.filter(status__in=[RouteStop.Status.PENDING, RouteStop.Status.ARRIVED]).exists():
        return
    has_failures = route.stops.filter(status=RouteStop.Status.FAILED).exists()
    route.status = DeliveryRoute.Status.COMPLETED_WITH_ISSUES if has_failures else DeliveryRoute.Status.COMPLETED
    route.completed_at = timezone.now()
    route.save(update_fields=["status", "completed_at", "updated_at"])
    RouteEvent.objects.create(
        route=route,
        event="completed",
        detail=f"{route.stops.count()} stops closed" + (" (with failures)" if has_failures else ""),
    )


def record_ping(*, driver: Driver, latitude, longitude) -> Driver:
    driver.current_latitude = latitude
    driver.current_longitude = longitude
    driver.last_ping_at = timezone.now()
    driver.save(update_fields=["current_latitude", "current_longitude", "last_ping_at", "updated_at"])
    DriverLocationPing.objects.create(driver=driver, latitude=latitude, longitude=longitude)
    return driver
