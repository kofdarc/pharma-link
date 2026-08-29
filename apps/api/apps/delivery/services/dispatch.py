"""
Bridge between the database and the pure solver in `routing.py`.

Responsibilities:
  - turn ready order fulfillments into solver Jobs (with real time windows)
  - turn online drivers into solver Vehicles
  - persist the resulting plan as DeliveryRoutes / RouteStops / RouteStopTasks
  - answer "what would this order cost this driver?" for the offer flow
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.common.geo import DROPOFF_SERVICE_MINUTES, PICKUP_SERVICE_MINUTES, travel_minutes
from apps.delivery.models import DeliveryRoute, Driver, RouteEvent, RouteStop, RouteStopTask
from apps.delivery.services import routing
from apps.orders.models import Order, OrderFulfillment

# Planning horizon anchor: all solver times are minutes after this instant.
DEFAULT_HORIZON_MINUTES = 12 * 60


def _minutes_between(anchor: datetime, moment: datetime) -> float:
    return (moment - anchor).total_seconds() / 60.0


def dispatchable_fulfillments():
    """
    Slices a driver could collect: accepted or ready, not yet picked up, and not already
    committed to a live route.
    """
    return (
        OrderFulfillment.objects.filter(
            status__in=[OrderFulfillment.Status.ACCEPTED, OrderFulfillment.Status.READY],
            order__fulfillment_type=Order.FulfillmentType.DELIVERY,
            order__status__in=[Order.Status.PENDING, Order.Status.CONFIRMED, Order.Status.READY],
        )
        .exclude(route_tasks__stop__route__status__in=[DeliveryRoute.Status.PROPOSED, DeliveryRoute.Status.OFFERED, DeliveryRoute.Status.ACTIVE])
        .select_related("order", "pharmacy")
        .prefetch_related("lines")
    )


def build_jobs(*, anchor: datetime | None = None, fulfillments=None) -> tuple[list[routing.Job], dict[str, dict]]:
    """
    One Job per order (not per pharmacy): all of an order's pickups plus its single dropoff,
    which is what lets the solver enforce "collect everything, then deliver once".
    """
    anchor = anchor or timezone.now()
    fulfillments = list(fulfillments if fulfillments is not None else dispatchable_fulfillments())

    grouped: dict[str, list[OrderFulfillment]] = {}
    for fulfillment in fulfillments:
        if fulfillment.order.latitude is None or fulfillment.pharmacy.latitude is None:
            continue
        grouped.setdefault(str(fulfillment.order_id), []).append(fulfillment)

    jobs: list[routing.Job] = []
    context: dict[str, dict] = {}

    for order_id, slices in grouped.items():
        order = slices[0].order
        pickups = []
        for fulfillment in slices:
            pharmacy = fulfillment.pharmacy
            ready_at = fulfillment.ready_at or (fulfillment.accepted_at or anchor) + timedelta(minutes=pharmacy.order_preparation_minutes)
            open_today = timezone.localtime(anchor).replace(hour=pharmacy.opens_at.hour, minute=pharmacy.opens_at.minute, second=0, microsecond=0)
            close_today = timezone.localtime(anchor).replace(hour=pharmacy.closes_at.hour, minute=pharmacy.closes_at.minute, second=0, microsecond=0)
            if close_today <= anchor:
                # Already past today's closing time (planning run at night, or a pharmacy
                # that closed early) - "today's" window is otherwise stamped onto a time
                # that has already passed, which collapses `latest` below to `earliest` (a
                # zero-width pickup window the solver can never satisfy) instead of correctly
                # reading as "reachable again once the pharmacy reopens tomorrow".
                open_today += timedelta(days=1)
                close_today += timedelta(days=1)
            earliest = max(_minutes_between(anchor, ready_at), _minutes_between(anchor, open_today), 0.0)
            latest = max(earliest, _minutes_between(anchor, close_today))
            pickups.append(
                routing.JobLeg(
                    location=routing.Location(key=f"pharmacy:{pharmacy.id}", latitude=float(pharmacy.latitude), longitude=float(pharmacy.longitude)),
                    units=sum(line.quantity for line in fulfillment.lines.all()),
                    earliest_minute=earliest,
                    latest_minute=latest,
                    service_minutes=PICKUP_SERVICE_MINUTES,
                    reference=str(fulfillment.id),
                )
            )

        if order.scheduled_for:
            dropoff_earliest = max(0.0, _minutes_between(anchor, order.window_start))
            dropoff_latest = _minutes_between(anchor, order.window_end)
        else:
            dropoff_earliest = 0.0
            dropoff_latest = float(settings.ASAP_DELIVERY_PROMISE_MINUTES)
        # A dropoff can never precede the last pickup being ready. When that pushes the
        # window forward (pharmacy still closed, or slow prep), keep the promised window's
        # full length rather than collapsing it to a fixed pad - a multi-pharmacy basket
        # needs real travel time between pickups, and 30 minutes flat isn't always enough
        # to reach more than one pharmacy before the customer.
        pushed_earliest = max(dropoff_earliest, max(leg.earliest_minute for leg in pickups))
        if pushed_earliest > dropoff_earliest:
            window_length = dropoff_latest - dropoff_earliest
            dropoff_latest = pushed_earliest + max(window_length, 30.0)
        dropoff_earliest = pushed_earliest

        job = routing.Job(
            job_id=order_id,
            pickups=tuple(pickups),
            dropoff_location=routing.Location(key=f"order:{order_id}", latitude=float(order.latitude), longitude=float(order.longitude)),
            dropoff_earliest_minute=dropoff_earliest,
            dropoff_latest_minute=dropoff_latest,
            dropoff_service_minutes=DROPOFF_SERVICE_MINUTES,
            priority=1 if order.prescription_id else 0,
        )
        jobs.append(job)
        context[order_id] = {"order": order, "fulfillments": {str(item.id): item for item in slices}}

    return jobs, context


def build_vehicles(*, anchor: datetime | None = None, drivers=None) -> tuple[list[routing.Vehicle], dict[str, Driver]]:
    anchor = anchor or timezone.now()
    drivers = list(drivers if drivers is not None else Driver.objects.filter(is_active=True, is_online=True))
    vehicles = []
    lookup = {}
    for driver in drivers:
        latitude, longitude = driver.position
        shift_end = float(DEFAULT_HORIZON_MINUTES)
        if driver.shift_end:
            end_today = timezone.localtime(anchor).replace(hour=driver.shift_end.hour, minute=driver.shift_end.minute, second=0, microsecond=0)
            shift_end = max(60.0, _minutes_between(anchor, end_today))
        vehicles.append(
            routing.Vehicle(
                vehicle_id=str(driver.id),
                start=routing.Location(key=f"driver:{driver.id}", latitude=latitude, longitude=longitude),
                capacity=driver.capacity_units,
                shift_start_minute=0.0,
                shift_end_minute=shift_end,
            )
        )
        lookup[str(driver.id)] = driver
    return vehicles, lookup


@transaction.atomic
def plan_and_persist(*, user=None, anchor: datetime | None = None) -> dict:
    """
    Full replan of everything not yet on the road. Existing PROPOSED/OFFERED routes are
    discarded first; ACTIVE routes are left alone so a driver mid-run is never rerouted
    out from under themselves.
    """
    anchor = anchor or timezone.now()
    DeliveryRoute.objects.filter(status__in=[DeliveryRoute.Status.PROPOSED, DeliveryRoute.Status.OFFERED]).delete()

    jobs, context = build_jobs(anchor=anchor)
    vehicles, drivers = build_vehicles(anchor=anchor)
    if not jobs:
        return {"detail": "Nothing to dispatch.", "summary": routing.summarise(routing.Plan([], []), [], vehicles), "routes": []}
    if not vehicles:
        return {"detail": "No drivers are online.", "summary": routing.summarise(routing.Plan([], []), jobs, []), "routes": []}

    plan = routing.solve(jobs, vehicles)
    summary = routing.summarise(plan, jobs, vehicles)

    created = []
    for route in plan.routes:
        if not route.stops:
            continue
        driver = drivers[route.vehicle.vehicle_id]
        naive_for_route = routing.naive_plan_distance([job for job in jobs if job.job_id in route.job_ids], [route.vehicle])
        record = DeliveryRoute.objects.create(
            driver=driver,
            status=DeliveryRoute.Status.PROPOSED,
            planned_distance_km=round(route.distance_km(), 2),
            planned_duration_minutes=int(_route_duration_minutes(route)),
            naive_distance_km=round(naive_for_route, 2),
            planner_notes=(
                f"{len(route.job_ids)} order(s), {len(route.stops)} stops. "
                f"{sum(1 for stop in route.stops if stop.kind == routing.PICKUP and len(stop.job_units) > 1)} shared pickup stop(s)."
            ),
        )
        _persist_stops(record, route, context, anchor)
        RouteEvent.objects.create(route=record, event="planned", detail=record.planner_notes, actor_user=user)
        created.append(record)

    return {
        "detail": f"Planned {len(created)} route(s) for {summary['assigned_jobs']} order(s).",
        "summary": summary,
        "routes": [str(record.id) for record in created],
    }


def _route_duration_minutes(route: routing.Route) -> float:
    if not route.stops:
        return 0.0
    last = route.stops[-1]
    return last.arrival_minute + last.service_minutes


def _persist_stops(record: DeliveryRoute, route: routing.Route, context: dict, anchor: datetime, start_sequence: int = 0) -> None:
    for index, stop in enumerate(route.stops, start=start_sequence + 1):
        if stop.kind == routing.PICKUP:
            fulfillment_ids = list(stop.references)
            first = next(
                (entry["fulfillments"][fid] for entry in context.values() for fid in fulfillment_ids if fid in entry["fulfillments"]),
                None,
            )
            pharmacy = first.pharmacy if first else None
            row = RouteStop.objects.create(
                route=record,
                sequence=index,
                kind=RouteStop.Kind.PICKUP,
                pharmacy=pharmacy,
                label=pharmacy.name if pharmacy else "Pickup",
                address=f"{pharmacy.address}, {pharmacy.area}" if pharmacy else "",
                latitude=stop.location.latitude,
                longitude=stop.location.longitude,
                units=stop.units,
                planned_arrival=anchor + timedelta(minutes=stop.arrival_minute),
                window_start=anchor + timedelta(minutes=stop.earliest_minute),
                window_end=anchor + timedelta(minutes=stop.latest_minute),
            )
            for fulfillment_id in fulfillment_ids:
                fulfillment = next((entry["fulfillments"][fulfillment_id] for entry in context.values() if fulfillment_id in entry["fulfillments"]), None)
                if fulfillment is None:
                    continue
                RouteStopTask.objects.create(stop=row, order_fulfillment=fulfillment, units=sum(line.quantity for line in fulfillment.lines.all()))
        else:
            order_id = next(iter(stop.job_units))
            order = context[order_id]["order"]
            row = RouteStop.objects.create(
                route=record,
                sequence=index,
                kind=RouteStop.Kind.DROPOFF,
                order=order,
                label=f"{order.contact_name} - {order.reference}",
                address=f"{order.address}, {order.area}",
                latitude=stop.location.latitude,
                longitude=stop.location.longitude,
                units=stop.units,
                planned_arrival=anchor + timedelta(minutes=stop.arrival_minute),
                window_start=anchor + timedelta(minutes=stop.earliest_minute),
                window_end=anchor + timedelta(minutes=stop.latest_minute),
            )
            for fulfillment in context[order_id]["fulfillments"].values():
                RouteStopTask.objects.create(stop=row, order_fulfillment=fulfillment, units=sum(line.quantity for line in fulfillment.lines.all()))


def marginal_cost_for_driver(*, driver: Driver, order: Order, anchor: datetime | None = None) -> dict | None:
    """
    "What does taking this order actually cost you?" - the number a driver sees before
    accepting. Computed as the true insertion delta against their current live route,
    which is why an order that fits a corridor they are already driving reads as ~0 km.
    """
    anchor = anchor or timezone.now()
    live = driver.routes.filter(status__in=[DeliveryRoute.Status.ACTIVE, DeliveryRoute.Status.OFFERED, DeliveryRoute.Status.PROPOSED]).first()
    fulfillments = list(order.fulfillments.filter(status__in=[OrderFulfillment.Status.ACCEPTED, OrderFulfillment.Status.READY]).select_related("pharmacy").prefetch_related("lines"))
    if not fulfillments:
        return None
    jobs, _context = build_jobs(anchor=anchor, fulfillments=fulfillments)
    if not jobs:
        return None
    vehicles, _lookup = build_vehicles(anchor=anchor, drivers=[driver])
    vehicle = vehicles[0]

    existing = routing.Route(vehicle=vehicle)
    if live:
        existing = _route_from_db(live, vehicle, anchor)

    attempt = routing.try_insert(existing, jobs[0])
    if attempt is None:
        return None
    marginal, stops = attempt
    return {
        "driver": str(driver.id),
        "driver_name": driver.full_name,
        "marginal_distance_km": round(marginal, 2),
        "total_distance_km": round(routing.route_distance(vehicle, stops), 2),
        "stops_after": len(stops),
        "shares_a_pickup": any(stop.kind == routing.PICKUP and len(stop.job_units) > 1 for stop in stops),
    }


def _route_from_db(record: DeliveryRoute, vehicle: routing.Vehicle, anchor: datetime) -> routing.Route:
    """Rebuilds the solver view of a route that already exists, keeping only unfinished stops."""
    stops = []
    for row in record.stops.filter(status__in=[RouteStop.Status.PENDING, RouteStop.Status.ARRIVED]).prefetch_related("tasks__order_fulfillment"):
        job_units: dict[str, int] = {}
        for task in row.tasks.all():
            key = str(task.order_fulfillment.order_id)
            job_units[key] = job_units.get(key, 0) + task.units
        stops.append(
            routing.Stop(
                kind=routing.PICKUP if row.kind == RouteStop.Kind.PICKUP else routing.DROPOFF,
                location=routing.Location(key=f"pharmacy:{row.pharmacy_id}" if row.pharmacy_id else f"order:{row.order_id}", latitude=float(row.latitude), longitude=float(row.longitude)),
                job_units=job_units,
                earliest_minute=max(0.0, _minutes_between(anchor, row.window_start)) if row.window_start else 0.0,
                latest_minute=_minutes_between(anchor, row.window_end) if row.window_end else float(DEFAULT_HORIZON_MINUTES),
                service_minutes=PICKUP_SERVICE_MINUTES if row.kind == RouteStop.Kind.PICKUP else DROPOFF_SERVICE_MINUTES,
                references=tuple(str(task.order_fulfillment_id) for task in row.tasks.all()),
            )
        )
    return routing.Route(vehicle=vehicle, stops=stops)


@transaction.atomic
def reoptimise_remaining(*, route: DeliveryRoute, user=None) -> dict:
    """
    Re-sequences only the stops a driver has not reached yet, starting from their live GPS
    position. Completed stops are frozen, so this is safe to hit mid-shift.
    """
    if route.driver is None:
        return {"detail": "This route has no driver."}
    anchor = timezone.now()
    vehicles, _lookup = build_vehicles(anchor=anchor, drivers=[route.driver])
    vehicle = vehicles[0]

    pending = list(route.stops.filter(status=RouteStop.Status.PENDING).prefetch_related("tasks__order_fulfillment__lines", "tasks__order_fulfillment__pharmacy"))
    if len(pending) < 3:
        return {"detail": "Too few stops left to be worth re-optimising."}

    fulfillment_ids = {task.order_fulfillment_id for stop in pending for task in stop.tasks.all()}
    fulfillments = list(
        OrderFulfillment.objects.filter(id__in=fulfillment_ids).select_related("order", "pharmacy").prefetch_related("lines")
    )
    jobs, context = build_jobs(anchor=anchor, fulfillments=fulfillments)
    if not jobs:
        return {"detail": "Nothing left to re-optimise."}

    before_km = float(route.planned_distance_km)
    plan = routing.solve(jobs, [vehicle])
    new_route = plan.routes[0]
    if not new_route.stops or plan.unassigned:
        return {"detail": "Could not find a feasible improvement; keeping the current order."}

    # Completed stops keep their sequence numbers; the new tail continues after them.
    offset = route.stops.exclude(status=RouteStop.Status.PENDING).aggregate(highest=Max("sequence"))["highest"] or 0
    route.stops.filter(status=RouteStop.Status.PENDING).delete()
    _persist_stops(route, new_route, context, anchor, start_sequence=offset)
    route.planned_distance_km = round(new_route.distance_km(), 2)
    route.planned_duration_minutes = int(_route_duration_minutes(new_route))
    route.plan_version += 1
    route.save(update_fields=["planned_distance_km", "planned_duration_minutes", "plan_version", "updated_at"])
    RouteEvent.objects.create(
        route=route,
        event="reoptimised",
        detail=f"{before_km:.1f} km -> {route.planned_distance_km} km for the remaining stops",
        actor_user=user,
    )
    return {
        "detail": "Remaining stops re-sequenced.",
        "previous_distance_km": before_km,
        "new_distance_km": float(route.planned_distance_km),
        "plan_version": route.plan_version,
    }
