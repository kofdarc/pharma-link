"""
Guarantees for the routing solver. These run against the pure functions, no database.

The claims worth defending:
  - hard constraints are never violated (precedence, capacity, time windows)
  - pickups at the same pharmacy are consolidated into one visit
  - marginal cost falls as a route grows (why batching works)
  - the optimised plan beats the naive one-trip-per-order baseline
"""

from django.test import SimpleTestCase

from apps.delivery.services import routing as R

# A compact synthetic Beirut: two pharmacies, customers spread along one corridor.
PHARM_A = R.Location(key="pharmacy:A", latitude=33.8975, longitude=35.4790)
PHARM_B = R.Location(key="pharmacy:B", latitude=33.8886, longitude=35.5175)
DEPOT = R.Location(key="driver:1", latitude=33.8930, longitude=35.4980)


def customer(index: int, latitude: float, longitude: float) -> R.Location:
    return R.Location(key=f"order:{index}", latitude=latitude, longitude=longitude)


def single_pickup_job(job_id: str, pharmacy: R.Location, drop: R.Location, units: int = 2, latest: float = 240.0) -> R.Job:
    return R.Job(
        job_id=job_id,
        pickups=(R.JobLeg(location=pharmacy, units=units, reference=f"f-{job_id}"),),
        dropoff_location=drop,
        dropoff_latest_minute=latest,
    )


def two_pickup_job(job_id: str, drop: R.Location, units: int = 2) -> R.Job:
    return R.Job(
        job_id=job_id,
        pickups=(
            R.JobLeg(location=PHARM_A, units=units, reference=f"fa-{job_id}"),
            R.JobLeg(location=PHARM_B, units=units, reference=f"fb-{job_id}"),
        ),
        dropoff_location=drop,
        dropoff_latest_minute=240.0,
    )


def vehicle(capacity: int = 60, shift_end: float = 720.0, vehicle_id: str = "1") -> R.Vehicle:
    return R.Vehicle(vehicle_id=vehicle_id, start=DEPOT, capacity=capacity, shift_end_minute=shift_end)


class RoutingFeasibilityTests(SimpleTestCase):
    def test_multi_pharmacy_job_is_assignable(self):
        """Regression: a basket split across two pharmacies must still be routable."""
        job = two_pickup_job("j1", customer(1, 33.8991, 35.4772))
        plan = R.solve([job], [vehicle()])

        self.assertEqual(plan.unassigned, [])
        stops = plan.routes[0].stops
        self.assertEqual(len(stops), 3)
        self.assertEqual(stops[-1].kind, R.DROPOFF)

    def test_pickups_always_precede_their_dropoff(self):
        jobs = [two_pickup_job("j1", customer(1, 33.8991, 35.4772)), two_pickup_job("j2", customer(2, 33.8901, 35.5199))]
        plan = R.solve(jobs, [vehicle()])

        for route in plan.routes:
            for job in jobs:
                collected = 0
                for stop in route.stops:
                    units = stop.job_units.get(job.job_id, 0)
                    if stop.kind == R.PICKUP:
                        collected += units
                    elif units:
                        self.assertGreaterEqual(collected, units, "delivered units that had not been picked up yet")

    def test_capacity_is_never_exceeded(self):
        jobs = [single_pickup_job(f"j{index}", PHARM_A, customer(index, 33.8991 + index * 0.001, 35.4772), units=8) for index in range(6)]
        plan = R.solve(jobs, [vehicle(capacity=16)])

        for route in plan.routes:
            load = 0
            for stop in route.stops:
                load += stop.units if stop.kind == R.PICKUP else -stop.units
                self.assertLessEqual(load, 16)
                self.assertGreaterEqual(load, 0)

    def test_impossible_time_window_is_left_unassigned_rather_than_violated(self):
        """A promise that cannot be kept must surface as unassigned, not as a late plan."""
        far_away = customer(9, 34.4367, 35.8497)  # Tripoli: ~80 km round trip from the depot
        job = single_pickup_job("j-impossible", PHARM_A, far_away, latest=5.0)
        plan = R.solve([job], [vehicle()])

        self.assertEqual([item.job_id for item in plan.unassigned], ["j-impossible"])
        self.assertEqual(plan.stop_count, 0)

    def test_evaluate_rejects_a_dropoff_placed_before_its_pickup(self):
        job = single_pickup_job("j1", PHARM_A, customer(1, 33.8991, 35.4772))
        bad_order = [R._dropoff_stop_for(job), R._pickup_stop_for(job.pickups[0], job)]

        feasible, _distance = R.evaluate(vehicle(), bad_order)

        self.assertFalse(feasible)


class ConsolidationTests(SimpleTestCase):
    def test_orders_from_the_same_pharmacy_share_one_pickup_stop(self):
        """The whole point: three customers, one visit to the pharmacy."""
        jobs = [
            single_pickup_job("j1", PHARM_A, customer(1, 33.8991, 35.4772)),
            single_pickup_job("j2", PHARM_A, customer(2, 33.8985, 35.4781)),
            single_pickup_job("j3", PHARM_A, customer(3, 33.8978, 35.4795)),
        ]
        plan = R.solve(jobs, [vehicle()])

        pickup_stops = [stop for route in plan.routes for stop in route.stops if stop.kind == R.PICKUP]
        self.assertEqual(len(pickup_stops), 1, "expected a single consolidated pickup, got one per order")
        self.assertEqual(len(pickup_stops[0].job_units), 3)
        self.assertEqual(pickup_stops[0].units, 6)

    def test_marginal_cost_falls_for_an_order_on_a_corridor_already_served(self):
        """
        Why batching pays: adding a nearby order to a route that already visits its
        pharmacy costs far less than serving it on its own.
        """
        first = single_pickup_job("j1", PHARM_A, customer(1, 33.8991, 35.4772))
        second = single_pickup_job("j2", PHARM_A, customer(2, 33.8990, 35.4774))

        empty = R.Route(vehicle=vehicle())
        cost_alone, _ = R.try_insert(empty, second)

        established = R.Route(vehicle=vehicle())
        _marginal, stops = R.try_insert(established, first)
        established.stops = stops
        cost_on_route, _ = R.try_insert(established, second)

        self.assertLess(cost_on_route, cost_alone)

    def test_summary_counts_avoided_pharmacy_visits(self):
        jobs = [
            single_pickup_job("j1", PHARM_A, customer(1, 33.8991, 35.4772)),
            single_pickup_job("j2", PHARM_A, customer(2, 33.8985, 35.4781)),
        ]
        plan = R.solve(jobs, [vehicle()])
        summary = R.summarise(plan, jobs, [vehicle()])

        self.assertEqual(summary["shared_pickup_stops"], 1)
        self.assertEqual(summary["pickup_visits_avoided"], 1)


class BaselineComparisonTests(SimpleTestCase):
    def test_optimised_plan_beats_one_trip_per_order(self):
        jobs = [
            two_pickup_job("j1", customer(1, 33.8991, 35.4772)),
            two_pickup_job("j2", customer(2, 33.8985, 35.4781)),
            single_pickup_job("j3", PHARM_A, customer(3, 33.8978, 35.4795)),
            single_pickup_job("j4", PHARM_B, customer(4, 33.8901, 35.5199)),
        ]
        vehicles = [vehicle(vehicle_id="1"), vehicle(vehicle_id="2")]
        plan = R.solve(jobs, vehicles)
        summary = R.summarise(plan, jobs, vehicles)

        self.assertEqual(summary["unassigned_jobs"], 0)
        self.assertLess(summary["optimised_distance_km"], summary["naive_distance_km"])
        self.assertGreater(summary["distance_saved_percent"], 0)

    def test_baseline_only_covers_assigned_orders(self):
        """
        The reported saving must not be inflated by orders the plan failed to serve, so the
        baseline is measured over the assigned set only.
        """
        servable = single_pickup_job("j-ok", PHARM_A, customer(1, 33.8991, 35.4772))
        impossible = single_pickup_job("j-bad", PHARM_A, customer(9, 34.4367, 35.8497), latest=5.0)
        vehicles = [vehicle()]

        plan = R.solve([servable, impossible], vehicles)
        summary = R.summarise(plan, [servable, impossible], vehicles)

        self.assertEqual(summary["unassigned_jobs"], 1)
        self.assertAlmostEqual(summary["naive_distance_km"], round(R.naive_plan_distance([servable], vehicles), 2), places=2)


class RelocationTests(SimpleTestCase):
    def test_removing_a_job_drops_pickup_stops_it_alone_justified(self):
        job = single_pickup_job("j1", PHARM_A, customer(1, 33.8991, 35.4772))
        route = R.Route(vehicle=vehicle())
        _marginal, stops = R.try_insert(route, job)
        route.stops = stops

        trimmed = R.remove_job(route, "j1")

        self.assertEqual(trimmed.stops, [])

    def test_removing_one_job_keeps_a_pickup_shared_with_another(self):
        jobs = [
            single_pickup_job("j1", PHARM_A, customer(1, 33.8991, 35.4772)),
            single_pickup_job("j2", PHARM_A, customer(2, 33.8985, 35.4781)),
        ]
        plan = R.solve(jobs, [vehicle()])
        route = next(item for item in plan.routes if item.stops)

        trimmed = R.remove_job(route, "j1")

        remaining_pickups = [stop for stop in trimmed.stops if stop.kind == R.PICKUP]
        self.assertEqual(len(remaining_pickups), 1)
        self.assertEqual(set(remaining_pickups[0].job_units), {"j2"})

    def test_solver_is_deterministic(self):
        jobs = [two_pickup_job("j1", customer(1, 33.8991, 35.4772)), single_pickup_job("j2", PHARM_B, customer(2, 33.8901, 35.5199))]
        first = R.solve(jobs, [vehicle(vehicle_id="1"), vehicle(vehicle_id="2")])
        second = R.solve(jobs, [vehicle(vehicle_id="1"), vehicle(vehicle_id="2")])

        self.assertEqual(
            [[stop.location.key for stop in route.stops] for route in first.routes],
            [[stop.location.key for stop in route.stops] for route in second.routes],
        )
