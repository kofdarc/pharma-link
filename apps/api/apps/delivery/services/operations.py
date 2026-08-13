from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.delivery.models import DeliveryRoute, Driver, DriverLocationPing, RouteEvent, RouteStop
from apps.orders.models import OrderFulfillment
from apps.orders.services.lifecycle import hand_over, mark_delivered


class OperationError(Exception):
    pass


@transaction.atomic
def accept_route(*, route: DeliveryRoute, driver: Driver) -> DeliveryRoute:
    route = DeliveryRoute.objects.select_for_update().get(id=route.id)
    if route.driver_id != driver.id:
        raise OperationError("This route was planned for another driver.")
    if route.status not in {DeliveryRoute.Status.PROPOSED, DeliveryRoute.Status.OFFERED}:
        raise OperationError("This route can no longer be accepted.")
    if driver.routes.filter(status=DeliveryRoute.Status.ACTIVE).exists():
        raise OperationError("Finish your active route first.")
    route.status = DeliveryRoute.Status.ACTIVE
    route.accepted_at = timezone.now()
    route.started_at = route.accepted_at
    route.save(update_fields=["status", "accepted_at", "started_at", "updated_at"])

    OrderFulfillment.objects.filter(route_tasks__stop__route=route).distinct().update(updated_at=timezone.now())
    RouteEvent.objects.create(route=route, event="accepted", detail=f"{driver.full_name} accepted the route", actor_user=driver.user)
    return route


@transaction.atomic
def arrive_at_stop(*, stop: RouteStop, driver: Driver) -> RouteStop:
    stop = RouteStop.objects.select_for_update().get(id=stop.id)
    if stop.route.driver_id != driver.id:
        raise OperationError("This stop is not on your route.")
    if stop.route.status != DeliveryRoute.Status.ACTIVE:
        raise OperationError("Accept the route before starting it.")
    if stop.status != RouteStop.Status.PENDING:
        raise OperationError("This stop is not pending.")
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
        raise OperationError("This stop is not on your route.")
    if stop.kind != RouteStop.Kind.PICKUP:
        raise OperationError("This stop is not a pickup.")
    if stop.status not in {RouteStop.Status.PENDING, RouteStop.Status.ARRIVED}:
        raise OperationError("This stop is already closed.")

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
        raise OperationError("This stop is not on your route.")
    if stop.kind != RouteStop.Kind.DROPOFF:
        raise OperationError("This stop is not a delivery.")
    if stop.status not in {RouteStop.Status.PENDING, RouteStop.Status.ARRIVED}:
        raise OperationError("This stop is already closed.")

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
    stop = RouteStop.objects.select_for_update().get(id=stop.id)
    if stop.route.driver_id != driver.id:
        raise OperationError("This stop is not on your route.")
    stop.status = RouteStop.Status.FAILED
    stop.failure_reason = reason[:255]
    stop.completed_at = timezone.now()
    stop.save(update_fields=["status", "failure_reason", "completed_at", "updated_at"])
    RouteEvent.objects.create(route=stop.route, stop=stop, event="failed", detail=reason[:255], actor_user=driver.user)
    _close_route_if_done(stop.route)
    return stop


def _close_route_if_done(route: DeliveryRoute) -> None:
    if route.stops.filter(status__in=[RouteStop.Status.PENDING, RouteStop.Status.ARRIVED]).exists():
        return
    route.status = DeliveryRoute.Status.COMPLETED
    route.completed_at = timezone.now()
    route.save(update_fields=["status", "completed_at", "updated_at"])
    RouteEvent.objects.create(route=route, event="completed", detail=f"{route.stops.count()} stops closed")


def record_ping(*, driver: Driver, latitude, longitude) -> Driver:
    driver.current_latitude = latitude
    driver.current_longitude = longitude
    driver.last_ping_at = timezone.now()
    driver.save(update_fields=["current_latitude", "current_longitude", "last_ping_at", "updated_at"])
    DriverLocationPing.objects.create(driver=driver, latitude=latitude, longitude=longitude)
    return driver
