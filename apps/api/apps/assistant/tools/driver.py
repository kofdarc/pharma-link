"""
One driver's own route.

Anchored on `ctx.user.driver_profile`. A driver sees the route assigned to them and nothing
else - not the dispatch board, not another driver's stops.
"""

from __future__ import annotations

from apps.assistant.tools.base import ToolContext
from apps.delivery.models import DeliveryRoute, RouteStop

MAX_ROWS = 8

# A stop the driver is done with, one way or another. Anything else is still ahead of them.
TERMINAL_STOP_STATUSES = {RouteStop.Status.DONE, RouteStop.Status.FAILED, RouteStop.Status.SKIPPED}


def _active_route(ctx: ToolContext):
    driver = getattr(ctx.user, "driver_profile", None)
    if driver is None:
        return None
    return (
        DeliveryRoute.objects.filter(driver=driver, status=DeliveryRoute.Status.ACTIVE)
        .prefetch_related("stops")
        .order_by("-created_at")
        .first()
    )


def _stop_payload(stop: RouteStop) -> dict:
    return {
        "sequence": stop.sequence,
        "kind": stop.get_kind_display(),
        "kind_code": stop.kind,
        "label": stop.label,
        "address": stop.address,
        "units": stop.units,
        "status": stop.get_status_display(),
        "planned_arrival": stop.planned_arrival.isoformat() if stop.planned_arrival else None,
    }


def my_route(ctx: ToolContext) -> dict:
    """The driver's current route and every stop still on it."""
    route = _active_route(ctx)
    if route is None:
        return {"has_route": False, "stops": [], "remaining": 0}

    remaining = [stop for stop in route.stops.all() if stop.status not in TERMINAL_STOP_STATUSES]
    remaining.sort(key=lambda stop: stop.sequence)
    return {
        "has_route": True,
        "status": route.get_status_display(),
        "planned_distance_km": str(route.planned_distance_km),
        "planned_duration_minutes": route.planned_duration_minutes,
        "total_stops": route.stops.count(),
        "remaining": len(remaining),
        "stops": [_stop_payload(stop) for stop in remaining[:MAX_ROWS]],
    }


def next_stop(ctx: ToolContext) -> dict:
    """
    Just the one stop they are heading to.

    A separate tool from `my_route` rather than a slice of it, because this is the question
    asked at a junction one-handed, and the answer wants to be one line - not a list the
    driver has to read down.
    """
    route = _active_route(ctx)
    if route is None:
        return {"has_route": False, "stop": None, "remaining": 0}

    remaining = [stop for stop in route.stops.all() if stop.status not in TERMINAL_STOP_STATUSES]
    remaining.sort(key=lambda stop: stop.sequence)
    if not remaining:
        return {"has_route": True, "stop": None, "remaining": 0}

    stop = remaining[0]
    payload = _stop_payload(stop)
    # The handover code only exists on a drop-off, and only matters at the door. Including it
    # on a pharmacy pickup would be noise at best and would train drivers to read past it.
    if stop.kind == RouteStop.Kind.DROPOFF and stop.order_id:
        codes = [task.order_fulfillment.handover_code for task in stop.tasks.select_related("order_fulfillment")]
        payload["handover_codes"] = [code for code in codes if code]
    return {"has_route": True, "stop": payload, "remaining": len(remaining)}
