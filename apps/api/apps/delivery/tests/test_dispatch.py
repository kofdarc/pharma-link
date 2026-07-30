"""
End-to-end dispatch: real orders in the database, through the solver, onto a driver, and
back out as delivered stock with an invoice.

The pure-solver tests prove the algorithm; these prove the wiring around it.
"""

from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import UserRole
from apps.delivery.models import DeliveryRoute, Driver, RouteStop
from apps.delivery.services.dispatch import build_jobs, marginal_cost_for_driver, plan_and_persist
from apps.delivery.services.operations import OperationError, accept_route, complete_dropoff, complete_pickup
from apps.inventory.models import InventoryBatch
from apps.inventory.services.stock import create_inventory_batch
from apps.medicines.models import Medicine
from apps.orders.models import Order, OrderFulfillment
from apps.orders.services.lifecycle import accept_fulfillment
from apps.orders.services.placement import place_order
from apps.pharmacies.models import Pharmacy

HAMRA = (33.8975, 35.4790)
ACHRAFIEH = (33.8886, 35.5175)


class DispatchTestCase(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        self.User = get_user_model()
        self.hamra = self._pharmacy("Cedar Care", "Hamra", HAMRA)
        self.achrafieh = self._pharmacy("Achrafieh Health", "Achrafieh", ACHRAFIEH)
        self.hamra_owner = self._user("owner@hamra.test", UserRole.PHARMACY_OWNER, pharmacy=self.hamra)
        self.achrafieh_owner = self._user("owner@ach.test", UserRole.PHARMACY_OWNER, pharmacy=self.achrafieh)

        self.panadol = Medicine.objects.create(brand_name="Panadol", strength="500mg", form="Tablet", regulated_price=Decimal("2.25"))
        self.nexium = Medicine.objects.create(brand_name="Nexium", strength="40mg", form="Tablet", regulated_price=Decimal("18.60"))
        self._stock(self.hamra, self.panadol, 50, self.hamra_owner)
        self._stock(self.achrafieh, self.nexium, 50, self.achrafieh_owner)

        self.driver_user = self._user("driver@test.test", UserRole.DRIVER)
        self.driver = Driver.objects.create(
            user=self.driver_user,
            full_name="Karim Saad",
            phone="+961-70-000-000",
            capacity_units=60,
            base_latitude=Decimal("33.8930"),
            base_longitude=Decimal("35.4980"),
            is_active=True,
            is_online=True,
        )

    def _pharmacy(self, name, area, coords):
        return Pharmacy.objects.create(
            name=name,
            area=area,
            city="Beirut",
            address=f"{area} street",
            phone="+961-1-000-000",
            latitude=Decimal(str(coords[0])),
            longitude=Decimal(str(coords[1])),
        )

    def _user(self, email, role, pharmacy=None):
        return self.User.objects.create_user(email=email, password="Password123!", role=role, pharmacy=pharmacy)

    def _stock(self, pharmacy, medicine, quantity, owner):
        return create_inventory_batch(
            user=owner,
            pharmacy=pharmacy,
            data={
                "medicine": medicine,
                "batch_number": f"{medicine.brand_name[:3]}-1",
                "initial_quantity": quantity,
                "expiry_date": timezone.localdate() + timezone.timedelta(days=200),
                "purchase_cost": Decimal("1.00"),
                "selling_price": medicine.regulated_price,
            },
        )

    def _shopper(self, index, coords):
        user = self._user(f"shopper{index}@test.test", UserRole.CUSTOMER)
        address = user.addresses.create(
            label="Home",
            contact_name=f"Shopper {index}",
            phone="+961-71-000-000",
            address=f"Street {index}",
            area="Hamra",
            city="Beirut",
            latitude=Decimal(str(coords[0])),
            longitude=Decimal(str(coords[1])),
            is_default=True,
        )
        return user, address

    def _place_and_accept(self, index, coords, items):
        user, address = self._shopper(index, coords)
        order = place_order(customer=user, items=items, address=address)
        for fulfillment in order.fulfillments.select_related("pharmacy"):
            owner = self.hamra_owner if fulfillment.pharmacy_id == self.hamra.id else self.achrafieh_owner
            accept_fulfillment(fulfillment=fulfillment, user=owner)
        return order


class PlanPersistenceTests(DispatchTestCase):
    def test_two_orders_from_the_same_pharmacy_share_one_pickup_stop(self):
        self._place_and_accept(1, (33.8991, 35.4772), [{"medicine": str(self.panadol.id), "quantity": 2}])
        self._place_and_accept(2, (33.8985, 35.4781), [{"medicine": str(self.panadol.id), "quantity": 3}])

        plan_and_persist()

        route = DeliveryRoute.objects.get()
        pickups = route.stops.filter(kind=RouteStop.Kind.PICKUP)
        self.assertEqual(pickups.count(), 1, "both orders come from one pharmacy, so there must be one visit")
        self.assertEqual(pickups.first().tasks.count(), 2)
        self.assertEqual(route.stops.filter(kind=RouteStop.Kind.DROPOFF).count(), 2)

    def test_multi_pharmacy_order_collects_everything_before_delivering(self):
        self._place_and_accept(
            1,
            (33.8991, 35.4772),
            [{"medicine": str(self.panadol.id), "quantity": 2}, {"medicine": str(self.nexium.id), "quantity": 1}],
        )

        plan_and_persist()

        route = DeliveryRoute.objects.get()
        sequence = list(route.stops.order_by("sequence").values_list("kind", flat=True))
        self.assertEqual(sequence.count(RouteStop.Kind.PICKUP), 2)
        self.assertEqual(sequence[-1], RouteStop.Kind.DROPOFF, "the delivery must come after both pickups")

    def test_route_records_the_baseline_it_beat(self):
        self._place_and_accept(1, (33.8991, 35.4772), [{"medicine": str(self.panadol.id), "quantity": 2}])
        self._place_and_accept(2, (33.8985, 35.4781), [{"medicine": str(self.panadol.id), "quantity": 2}])

        result = plan_and_persist()
        route = DeliveryRoute.objects.get()

        self.assertGreater(float(route.naive_distance_km), 0)
        self.assertLessEqual(float(route.planned_distance_km), float(route.naive_distance_km))
        self.assertEqual(result["summary"]["unassigned_jobs"], 0)

    def test_replanning_replaces_proposals_without_touching_an_active_route(self):
        self._place_and_accept(1, (33.8991, 35.4772), [{"medicine": str(self.panadol.id), "quantity": 2}])
        plan_and_persist()
        route = DeliveryRoute.objects.get()
        accept_route(route=route, driver=self.driver)

        self._place_and_accept(2, (33.8985, 35.4781), [{"medicine": str(self.panadol.id), "quantity": 2}])
        plan_and_persist()

        route.refresh_from_db()
        self.assertEqual(route.status, DeliveryRoute.Status.ACTIVE, "a driver mid-run must not be rerouted")
        self.assertEqual(DeliveryRoute.objects.count(), 2)

    def test_orders_already_on_a_live_route_are_not_planned_twice(self):
        self._place_and_accept(1, (33.8991, 35.4772), [{"medicine": str(self.panadol.id), "quantity": 2}])
        plan_and_persist()
        route = DeliveryRoute.objects.get()
        accept_route(route=route, driver=self.driver)

        jobs, _context = build_jobs()

        self.assertEqual(jobs, [], "the committed order should no longer be dispatchable")

    def test_pending_orders_are_not_dispatchable_until_a_pharmacy_accepts(self):
        user, address = self._shopper(1, (33.8991, 35.4772))
        place_order(customer=user, items=[{"medicine": str(self.panadol.id), "quantity": 2}], address=address)

        jobs, _context = build_jobs()

        self.assertEqual(jobs, [])

    def test_marginal_cost_is_offered_per_driver(self):
        order = self._place_and_accept(1, (33.8991, 35.4772), [{"medicine": str(self.panadol.id), "quantity": 2}])

        offer = marginal_cost_for_driver(driver=self.driver, order=order)

        self.assertIsNotNone(offer)
        self.assertGreater(offer["marginal_distance_km"], 0)
        self.assertEqual(offer["driver_name"], "Karim Saad")


class DriverOperationTests(DispatchTestCase):
    def setUp(self):
        super().setUp()
        self.order = self._place_and_accept(1, (33.8991, 35.4772), [{"medicine": str(self.panadol.id), "quantity": 4}])
        plan_and_persist()
        self.route = DeliveryRoute.objects.get()

    def test_full_run_delivers_the_order_and_writes_an_invoice(self):
        accept_route(route=self.route, driver=self.driver)
        pickup = self.route.stops.get(kind=RouteStop.Kind.PICKUP)
        fulfillment = self.order.fulfillments.get()

        complete_pickup(stop=pickup, driver=self.driver, handover_codes={str(fulfillment.id): fulfillment.handover_code})
        dropoff = self.route.stops.get(kind=RouteStop.Kind.DROPOFF)
        complete_dropoff(stop=dropoff, driver=self.driver)

        fulfillment.refresh_from_db()
        self.order.refresh_from_db()
        self.route.refresh_from_db()
        batch = InventoryBatch.objects.get(medicine=self.panadol, pharmacy=self.hamra)

        self.assertEqual(fulfillment.status, OrderFulfillment.Status.DELIVERED)
        self.assertEqual(self.order.status, Order.Status.DELIVERED)
        self.assertEqual(self.route.status, DeliveryRoute.Status.COMPLETED)
        self.assertIsNotNone(fulfillment.sale)
        self.assertEqual(fulfillment.sale.total, Decimal("9.00"))
        self.assertEqual(batch.current_quantity, 46, "stock leaves the shelf only at pickup")
        self.assertEqual(batch.reserved_quantity, 0)

    def test_a_wrong_handover_code_blocks_the_pickup(self):
        accept_route(route=self.route, driver=self.driver)
        pickup = self.route.stops.get(kind=RouteStop.Kind.PICKUP)
        fulfillment = self.order.fulfillments.get()

        with self.assertRaises(Exception):
            complete_pickup(stop=pickup, driver=self.driver, handover_codes={str(fulfillment.id): "000000"})

        fulfillment.refresh_from_db()
        self.assertNotEqual(fulfillment.status, OrderFulfillment.Status.PICKED_UP)

    def test_a_driver_cannot_touch_another_driver_s_stop(self):
        other_user = self._user("other@test.test", UserRole.DRIVER)
        other = Driver.objects.create(
            user=other_user,
            full_name="Someone Else",
            phone="+961-70-111-111",
            base_latitude=Decimal("33.89"),
            base_longitude=Decimal("35.50"),
            is_active=True,
            is_online=True,
        )
        accept_route(route=self.route, driver=self.driver)
        pickup = self.route.stops.get(kind=RouteStop.Kind.PICKUP)

        with self.assertRaises(OperationError):
            complete_pickup(stop=pickup, driver=other)

    def test_a_route_cannot_be_accepted_twice(self):
        accept_route(route=self.route, driver=self.driver)

        with self.assertRaises(OperationError):
            accept_route(route=self.route, driver=self.driver)

    def test_delivery_before_pickup_is_refused(self):
        accept_route(route=self.route, driver=self.driver)
        dropoff = self.route.stops.get(kind=RouteStop.Kind.DROPOFF)

        complete_dropoff(stop=dropoff, driver=self.driver)
        fulfillment = self.order.fulfillments.get()
        fulfillment.refresh_from_db()

        # The stop closes, but nothing can be marked delivered that was never collected.
        self.assertNotEqual(fulfillment.status, OrderFulfillment.Status.DELIVERED)
