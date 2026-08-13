"""
Delivery routing for baskets sourced from several pharmacies.

THE PROBLEM
    An order can have items from 3 pharmacies. The naive plan sends one driver to those 3
    pharmacies and then to that one customer: 4 stops to serve 1 person. Do that for 20
    orders and you burn 80 stops.

THE MODEL
    This is a Pickup-and-Delivery Problem with Time Windows (PDPTW) plus one twist that
    matters enormously in practice: pickups CONSOLIDATE. Two orders that both need
    something from Cedar Care share a single stop there. So the planner works on stops
    keyed by location, each serving a set of jobs, rather than on per-order tours.

    Formally, a job j has pickup locations P(j) and one dropoff d(j), and we need:
      - precedence: every stop in P(j) precedes d(j) on the same route
      - capacity:   load never exceeds the vehicle's capacity
      - windows:    every stop is served within [earliest, latest]
    minimising   total_distance + DRIVER_FIXED_COST * routes_used.
    The fixed cost per route is what makes the solver prefer stacking work onto an
    existing driver over waking up a new one.

THE ALGORITHM
    1. Regret-ordered parallel insertion.
       Jobs are inserted hardest-first (tightest window, most pickups). For each job we
       try every position for its dropoff; given that position, each required pickup is
       either MERGED into an existing stop at the same pharmacy or inserted at its own
       cheapest feasible position before the dropoff. Merging is why marginal cost falls
       as a route grows: the 5th order through Hamra can cost almost nothing to add.
    2. Relocation local search (or-opt over whole jobs).
       Repeatedly pull the job with the worst removal gain out of its route and re-insert
       it wherever it is now cheapest, including on another driver. Accept strict
       improvements only; stop at a fixed iteration budget so planning stays interactive.

    Everything is deterministic and dependency-free: no solver library, no routing API.
    `plan_routes` is pure - it takes dataclasses and returns dataclasses - which is what
    makes the guarantees in tests/test_routing.py checkable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import permutations

from apps.common.geo import road_km, travel_minutes

# Cost, in "km-equivalents", of putting one more driver on the road. Set high enough that
# the solver will happily add a 3 km detour to an existing route instead of opening a new one.
DRIVER_FIXED_COST_KM = 12.0

# Guard rails so a shopper is never the victim of perfect global efficiency.
MAX_STOPS_PER_ROUTE = 14
MAX_RELOCATION_PASSES = 6

PICKUP = "PICKUP"
DROPOFF = "DROPOFF"


@dataclass(frozen=True)
class Location:
    key: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class JobLeg:
    """One pickup requirement: `units` to collect at `location`."""

    location: Location
    units: int
    earliest_minute: float = 0.0
    latest_minute: float = 24 * 60.0
    service_minutes: float = 6.0
    reference: str = ""


@dataclass(frozen=True)
class Job:
    job_id: str
    pickups: tuple[JobLeg, ...]
    dropoff_location: Location
    dropoff_earliest_minute: float = 0.0
    dropoff_latest_minute: float = 24 * 60.0
    dropoff_service_minutes: float = 4.0
    priority: int = 0

    @property
    def units(self) -> int:
        return sum(leg.units for leg in self.pickups)


@dataclass(frozen=True)
class Vehicle:
    vehicle_id: str
    start: Location
    capacity: int
    shift_start_minute: float = 0.0
    shift_end_minute: float = 24 * 60.0


@dataclass
class Stop:
    kind: str
    location: Location
    # job_id -> units handled at this stop. A pickup stop can serve several jobs at once.
    job_units: dict[str, int] = field(default_factory=dict)
    earliest_minute: float = 0.0
    latest_minute: float = 24 * 60.0
    service_minutes: float = 5.0
    arrival_minute: float = 0.0
    references: tuple[str, ...] = ()

    @property
    def units(self) -> int:
        return sum(self.job_units.values())

    def clone(self) -> "Stop":
        return Stop(
            kind=self.kind,
            location=self.location,
            job_units=dict(self.job_units),
            earliest_minute=self.earliest_minute,
            latest_minute=self.latest_minute,
            service_minutes=self.service_minutes,
            arrival_minute=self.arrival_minute,
            references=self.references,
        )


@dataclass
class Route:
    vehicle: Vehicle
    stops: list[Stop] = field(default_factory=list)

    @property
    def job_ids(self) -> set[str]:
        return {job_id for stop in self.stops for job_id in stop.job_units}

    def clone(self) -> "Route":
        return Route(vehicle=self.vehicle, stops=[stop.clone() for stop in self.stops])

    def distance_km(self) -> float:
        return route_distance(self.vehicle, self.stops)


@dataclass
class Plan:
    routes: list[Route]
    unassigned: list[Job]

    @property
    def distance_km(self) -> float:
        return sum(route.distance_km() for route in self.routes if route.stops)

    @property
    def stop_count(self) -> int:
        return sum(len(route.stops) for route in self.routes)

    def cost(self) -> float:
        used = [route for route in self.routes if route.stops]
        return self.distance_km + DRIVER_FIXED_COST_KM * len(used)


def leg_km(a: Location, b: Location) -> float:
    if a.key == b.key:
        return 0.0
    return road_km(a.latitude, a.longitude, b.latitude, b.longitude)


def route_distance(vehicle: Vehicle, stops: list[Stop]) -> float:
    if not stops:
        return 0.0
    total = leg_km(vehicle.start, stops[0].location)
    for previous, current in zip(stops, stops[1:]):
        total += leg_km(previous.location, current.location)
    return total


def evaluate(vehicle: Vehicle, stops: list[Stop]) -> tuple[bool, float]:
    """
    Forward pass over a candidate stop order. Returns (feasible, distance_km) and writes
    arrival times onto the stops. Enforces capacity, precedence and time windows.
    """
    if len(stops) > MAX_STOPS_PER_ROUTE:
        return False, 0.0

    seen_pickups: dict[str, int] = {}
    load = 0
    clock = vehicle.shift_start_minute
    position = vehicle.start
    distance = 0.0

    for stop in stops:
        hop = leg_km(position, stop.location)
        distance += hop
        clock += travel_minutes(hop)
        clock = max(clock, stop.earliest_minute)
        if clock > stop.latest_minute:
            return False, 0.0

        if stop.kind == PICKUP:
            load += stop.units
            if load > vehicle.capacity:
                return False, 0.0
            for job_id, units in stop.job_units.items():
                seen_pickups[job_id] = seen_pickups.get(job_id, 0) + units
        else:
            for job_id, units in stop.job_units.items():
                # Precedence: nothing can be dropped off before it has been collected.
                if seen_pickups.get(job_id, 0) < units:
                    return False, 0.0
            load -= stop.units
            if load < 0:
                return False, 0.0

        stop.arrival_minute = clock
        clock += stop.service_minutes
        position = stop.location

    if clock > vehicle.shift_end_minute:
        return False, 0.0
    return True, distance


def _pickup_stop_for(leg: JobLeg, job: Job) -> Stop:
    return Stop(
        kind=PICKUP,
        location=leg.location,
        job_units={job.job_id: leg.units},
        earliest_minute=leg.earliest_minute,
        latest_minute=leg.latest_minute,
        service_minutes=leg.service_minutes,
        references=(leg.reference,) if leg.reference else (),
    )


def _dropoff_stop_for(job: Job) -> Stop:
    return Stop(
        kind=DROPOFF,
        location=job.dropoff_location,
        job_units={job.job_id: job.units},
        earliest_minute=job.dropoff_earliest_minute,
        latest_minute=job.dropoff_latest_minute,
        service_minutes=job.dropoff_service_minutes,
        references=(job.job_id,),
    )


# Pickup orderings are enumerated exhaustively up to this many pickups per job. Baskets
# are split across 1-3 pharmacies in practice, so this is complete in the real cases and
# degrades to a single distance-ordered pass only for pathological baskets.
MAX_PERMUTED_PICKUPS = 4


def _place_pickups(route: Route, job: Job, stops: list[Stop], dropoff_position: int, legs: tuple[JobLeg, ...]) -> tuple[list[Stop], int] | None:
    """
    Inserts every pickup before the dropoff, one leg at a time, choosing each position by
    ADDED DISTANCE only.

    Feasibility is deliberately not tested here. A half-built candidate is always infeasible
    by construction - the dropoff needs the job's full unit count, which is not collected
    until the last pickup is placed - so checking it mid-way would reject every
    multi-pharmacy job. The completed candidate is validated by the caller.
    """
    for leg in legs:
        candidates: list[tuple[float, list[Stop]]] = []

        # Merging into an existing visit to the same pharmacy adds zero travel: this is the
        # consolidation that keeps marginal cost low as a route fills up.
        merge_index = next(
            (index for index in range(dropoff_position) if stops[index].kind == PICKUP and stops[index].location.key == leg.location.key),
            None,
        )
        if merge_index is not None:
            merged = [stop.clone() for stop in stops]
            target = merged[merge_index]
            target.job_units[job.job_id] = target.job_units.get(job.job_id, 0) + leg.units
            target.earliest_minute = max(target.earliest_minute, leg.earliest_minute)
            target.latest_minute = min(target.latest_minute, leg.latest_minute)
            target.service_minutes = max(target.service_minutes, leg.service_minutes)
            target.references = tuple(dict.fromkeys(target.references + ((leg.reference,) if leg.reference else ())))
            candidates.append((route_distance(route.vehicle, merged), merged))

        for index in range(dropoff_position + 1):
            trial = [stop.clone() for stop in stops]
            trial.insert(index, _pickup_stop_for(leg, job))
            candidates.append((route_distance(route.vehicle, trial), trial))

        if not candidates:
            return None
        candidates.sort(key=lambda entry: entry[0])
        stops = candidates[0][1]
        dropoff_position = next(index for index, stop in enumerate(stops) if stop.kind == DROPOFF and job.job_id in stop.job_units)

    return stops, dropoff_position


def try_insert(route: Route, job: Job) -> tuple[float, list[Stop]] | None:
    """
    Cheapest feasible way to add `job` to `route`, or None if it cannot be served.

    Enumerates every position for the dropoff and every ordering of the pickups, places
    the pickups by cheapest added distance, then validates the finished route once against
    capacity, precedence and time windows. Returns the marginal distance, which is the
    number the offer flow shows a driver.
    """
    base_feasible, base_distance = evaluate(route.vehicle, route.stops)
    if route.stops and not base_feasible:
        return None

    if len(job.pickups) <= MAX_PERMUTED_PICKUPS:
        orderings = list(permutations(job.pickups))
    else:
        orderings = [tuple(sorted(job.pickups, key=lambda leg: leg.earliest_minute))]

    best: tuple[float, list[Stop]] | None = None
    for dropoff_index in range(len(route.stops) + 1):
        for legs in orderings:
            stops = [stop.clone() for stop in route.stops]
            stops.insert(dropoff_index, _dropoff_stop_for(job))
            placed = _place_pickups(route, job, stops, dropoff_index, legs)
            if placed is None:
                continue
            candidate_stops, _position = placed
            feasible, distance = evaluate(route.vehicle, candidate_stops)
            if not feasible:
                continue
            marginal = distance - base_distance
            if best is None or marginal < best[0]:
                best = (marginal, candidate_stops)

    return best


def remove_job(route: Route, job_id: str) -> Route:
    """Pulls a job out, discarding pickup stops that no longer serve anyone."""
    stops = []
    for stop in route.stops:
        clone = stop.clone()
        if job_id in clone.job_units:
            del clone.job_units[job_id]
            if not clone.job_units:
                continue
        stops.append(clone)
    return Route(vehicle=route.vehicle, stops=stops)


def _job_difficulty(job: Job) -> tuple:
    """Hardest first: tight windows and multi-pharmacy baskets have the fewest valid slots."""
    window = job.dropoff_latest_minute - job.dropoff_earliest_minute
    return (-job.priority, window, -len(job.pickups), job.dropoff_earliest_minute)


def solve(jobs: list[Job], vehicles: list[Vehicle]) -> Plan:
    """
    Entry point: regret-ordered insertion followed by job relocation.
    Pure and deterministic - same inputs always give the same plan.
    """
    routes = [Route(vehicle=vehicle) for vehicle in vehicles]
    unassigned: list[Job] = []

    for job in sorted(jobs, key=_job_difficulty):
        options = []
        for index, route in enumerate(routes):
            attempt = try_insert(route, job)
            if attempt is None:
                continue
            marginal, stops = attempt
            # Opening a fresh route carries the driver fixed cost, so a busy route wins ties.
            penalty = DRIVER_FIXED_COST_KM if not route.stops else 0.0
            options.append((marginal + penalty, index, stops))
        if not options:
            unassigned.append(job)
            continue
        options.sort(key=lambda entry: entry[0])
        _score, index, stops = options[0]
        routes[index].stops = stops

    _relocate(routes, {job.job_id: job for job in jobs})
    return Plan(routes=routes, unassigned=unassigned)


def _relocate(routes: list[Route], job_index: dict[str, Job]) -> None:
    """
    Or-opt over whole jobs. Insertion order is a guess; this fixes the cases where a job
    that arrived early sits on the wrong driver once the rest of the day is known.
    """

    def total_cost(candidate_routes: list[Route]) -> float:
        used = [route for route in candidate_routes if route.stops]
        return sum(route.distance_km() for route in used) + DRIVER_FIXED_COST_KM * len(used)

    for _pass in range(MAX_RELOCATION_PASSES):
        improved = False
        current_cost = total_cost(routes)
        job_locations = [(index, job_id) for index, route in enumerate(routes) for job_id in sorted(route.job_ids)]

        for source_index, job_id in job_locations:
            job = job_index.get(job_id)
            if job is None or job_id not in routes[source_index].job_ids:
                continue
            trimmed = remove_job(routes[source_index], job_id)
            if not evaluate(trimmed.vehicle, trimmed.stops)[0] and trimmed.stops:
                continue

            best_move = None
            for target_index, route in enumerate(routes):
                candidate_route = trimmed if target_index == source_index else route
                attempt = try_insert(candidate_route, job)
                if attempt is None:
                    continue
                _marginal, stops = attempt
                trial = [existing.clone() for existing in routes]
                trial[source_index] = trimmed.clone()
                trial[target_index] = Route(vehicle=routes[target_index].vehicle, stops=stops)
                candidate_cost = total_cost(trial)
                if candidate_cost < current_cost - 1e-9 and (best_move is None or candidate_cost < best_move[0]):
                    best_move = (candidate_cost, target_index, stops, trimmed.clone())

            if best_move is not None:
                current_cost, target_index, stops, trimmed_clone = best_move
                routes[source_index] = trimmed_clone
                routes[target_index] = Route(vehicle=routes[target_index].vehicle, stops=stops)
                improved = True

        if not improved:
            break


def naive_plan_distance(jobs: list[Job], vehicles: list[Vehicle]) -> float:
    """
    The baseline this system exists to beat: one dedicated trip per order, visiting that
    order's pharmacies nearest-first and then the customer. Reported next to the optimised
    plan so the saving is a measured number rather than a claim.
    """
    if not vehicles:
        return 0.0
    depot = vehicles[0].start
    total = 0.0
    for job in jobs:
        position = depot
        remaining = list(job.pickups)
        while remaining:
            nearest = min(remaining, key=lambda leg: leg_km(position, leg.location))
            total += leg_km(position, nearest.location)
            position = nearest.location
            remaining.remove(nearest)
        total += leg_km(position, job.dropoff_location)
    return total


def summarise(plan: Plan, jobs: list[Job], vehicles: list[Vehicle]) -> dict:
    used = [route for route in plan.routes if route.stops]
    assigned_ids = {job_id for route in used for job_id in route.job_ids}
    # The baseline must cover exactly the jobs the plan actually serves, otherwise the
    # "saving" would just be measuring the orders we failed to assign.
    assigned_jobs = [job for job in jobs if job.job_id in assigned_ids]
    naive = naive_plan_distance(assigned_jobs, vehicles)
    optimised = plan.distance_km
    merged_pickups = sum(1 for route in used for stop in route.stops if stop.kind == PICKUP and len(stop.job_units) > 1)
    total_pickup_stops = sum(1 for route in used for stop in route.stops if stop.kind == PICKUP)
    pickup_visits_if_unbatched = sum(len(job.pickups) for job in assigned_jobs)
    return {
        "jobs": len(jobs),
        "assigned_jobs": len(assigned_ids),
        "unassigned_jobs": len(plan.unassigned),
        "routes_used": len(used),
        "drivers_available": len(vehicles),
        "stops": plan.stop_count,
        "pickup_stops": total_pickup_stops,
        "shared_pickup_stops": merged_pickups,
        "pickup_visits_avoided": max(0, pickup_visits_if_unbatched - total_pickup_stops),
        "baseline_scope": "one dedicated trip per assigned order",
        "naive_distance_km": round(naive, 2),
        "optimised_distance_km": round(optimised, 2),
        "distance_saved_km": round(max(0.0, naive - optimised), 2),
        "distance_saved_percent": round((max(0.0, naive - optimised) / naive * 100) if naive else 0.0, 1),
    }
