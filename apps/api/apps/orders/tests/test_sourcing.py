"""
Basket sourcing, stock reservations and the public quantity cap.

What must hold:
  - a basket one pharmacy can fill is never split (fewer pickups = shorter routes)
  - a basket no single pharmacy can fill is split, and covered as far as stock allows
  - confirmed orders hold real stock, so two shoppers cannot claim the same box
  - shortfalls are recorded as unmet demand instead of silently dropped
"""

from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import UserRole
from apps.inventory.models import InventoryBatch
from apps.inventory.services.stock import create_inventory_batch
from apps.medicines.models import MarketStatus, Medicine, PriceRegime, ProductCategory
from apps.orders.models import Order, OrderFulfillment, StockReservation, UnmetDemandSignal
from apps.orders.services.lifecycle import hand_over, reject_fulfillment
from apps.orders.services.placement import OrderError, expire_stale_reservations, place_order
from apps.orders.services.sourcing import plan_basket
from apps.pharmacies.models import Pharmacy

# Two pharmacies ~3.5 km apart, shopper next door to the first.
HAMRA = (33.8975, 35.4790)
ACHRAFIEH = (33.8886, 35.5175)
SHOPPER_HOME = (33.8991, 35.4772)


def make_pharmacy(name, area, coords, *, rating="4.5", count=20, reliability="98.0") -> Pharmacy:
    return Pharmacy.objects.create(
        name=name,
        area=area,
        city="Beirut",
        address=f"{area} street",
        phone="+961-1-000-000",
        latitude=Decimal(str(coords[0])),
        longitude=Decimal(str(coords[1])),
        rating_average=Decimal(rating),
        rating_count=count,
        fulfillment_success_rate=Decimal(reliability),
    )


class SourcingTestCase(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.hamra = make_pharmacy("Cedar Care", "Hamra", HAMRA)
        self.achrafieh = make_pharmacy("Achrafieh Health", "Achrafieh", ACHRAFIEH, rating="4.9", count=90)
        self.hamra_owner = User.objects.create_user(email="owner@hamra.test", password="Password123!", role=UserRole.PHARMACY_OWNER, pharmacy=self.hamra)
        self.achrafieh_owner = User.objects.create_user(email="owner@ach.test", password="Password123!", role=UserRole.PHARMACY_OWNER, pharmacy=self.achrafieh)
        self.shopper = User.objects.create_user(email="shopper@test.test", password="Password123!", role=UserRole.CUSTOMER)

        self.panadol = Medicine.objects.create(brand_name="Panadol", strength="500mg", form="Tablet", regulated_price=Decimal("2.25"))
        self.nexium = Medicine.objects.create(brand_name="Nexium", strength="40mg", form="Tablet", regulated_price=Decimal("18.60"))
        self.omega = Medicine.objects.create(
            brand_name="Omega 3", strength="1000mg", form="Softgel", category=ProductCategory.SUPPLEMENT, price_regime=PriceRegime.FREE, regulated_price=None
        )

        self.address = self.shopper.addresses.create(
            label="Home",
            contact_name="Shopper",
            phone="+961-71-000-000",
            address="Hamra",
            area="Hamra",
            city="Beirut",
            latitude=Decimal(str(SHOPPER_HOME[0])),
            longitude=Decimal(str(SHOPPER_HOME[1])),
            is_default=True,
        )

    def stock(self, pharmacy, medicine, quantity, *, price=None, owner=None):
        return create_inventory_batch(
            user=owner or (self.hamra_owner if pharmacy == self.hamra else self.achrafieh_owner),
            pharmacy=pharmacy,
            data={
                "medicine": medicine,
                "batch_number": f"{medicine.brand_name[:3]}-1",
                "initial_quantity": quantity,
                "expiry_date": timezone.localdate() + timezone.timedelta(days=200),
                "purchase_cost": Decimal("1.00"),
                "selling_price": price if price is not None else (medicine.regulated_price or Decimal("15.00")),
                "low_stock_threshold": 3,
            },
        )

    def quote(self, items):
        return plan_basket(items=items, latitude=SHOPPER_HOME[0], longitude=SHOPPER_HOME[1])


class BasketSplittingTests(SourcingTestCase):
    def test_one_pharmacy_that_can_cover_everything_is_used_alone(self):
        self.stock(self.hamra, self.panadol, 20)
        self.stock(self.hamra, self.nexium, 20)
        self.stock(self.achrafieh, self.panadol, 20)
        self.stock(self.achrafieh, self.nexium, 20)

        plan = self.quote([{"medicine": str(self.panadol.id), "quantity": 2}, {"medicine": str(self.nexium.id), "quantity": 1}])

        self.assertEqual(plan["pharmacy_count"], 1)
        self.assertEqual(plan["unfulfilled"], [])
        self.assertIn("whole basket in one stop", " ".join(plan["explanation"]))

    def test_nearest_pharmacy_wins_when_both_can_cover(self):
        self.stock(self.hamra, self.panadol, 20)
        self.stock(self.achrafieh, self.panadol, 20)

        plan = self.quote([{"medicine": str(self.panadol.id), "quantity": 2}])

        self.assertEqual(plan["allocations"][0]["pharmacy"], self.hamra.id)

    def test_basket_is_split_only_when_no_pharmacy_can_cover_it(self):
        self.stock(self.hamra, self.panadol, 20)
        self.stock(self.achrafieh, self.nexium, 20)

        plan = self.quote([{"medicine": str(self.panadol.id), "quantity": 2}, {"medicine": str(self.nexium.id), "quantity": 1}])

        self.assertEqual(plan["pharmacy_count"], 2)
        self.assertEqual(plan["unfulfilled"], [])

    def test_shortfall_is_reported_rather_than_hidden(self):
        self.stock(self.hamra, self.panadol, 2)

        plan = self.quote([{"medicine": str(self.panadol.id), "quantity": 5}])

        self.assertEqual(len(plan["unfulfilled"]), 1)
        self.assertEqual(plan["unfulfilled"][0]["quantity_short"], 3)

    def test_regulated_price_is_used_regardless_of_what_a_pharmacy_entered(self):
        # A pharmacy cannot undercut or inflate a MoPH price, so the quote must show the official one.
        self.stock(self.hamra, self.panadol, 20)

        plan = self.quote([{"medicine": str(self.panadol.id), "quantity": 2}])
        line = plan["allocations"][0]["lines"][0]

        self.assertTrue(line["is_price_regulated"])
        self.assertEqual(line["unit_price"], self.panadol.regulated_price)

    def test_free_priced_items_use_the_pharmacy_price(self):
        self.stock(self.hamra, self.omega, 10, price=Decimal("22.00"))

        plan = self.quote([{"medicine": str(self.omega.id), "quantity": 1}])
        line = plan["allocations"][0]["lines"][0]

        self.assertFalse(line["is_price_regulated"])
        self.assertEqual(line["unit_price"], Decimal("22.00"))

    @override_settings(PUBLIC_MAX_QUANTITY_PER_ITEM=4)
    def test_visible_quantity_is_capped_so_stock_depth_stays_private(self):
        self.stock(self.hamra, self.panadol, 500)

        plan = self.quote([{"medicine": str(self.panadol.id), "quantity": 10}])

        self.assertEqual(plan["allocations"][0]["lines"][0]["quantity"], 4)
        self.assertEqual(plan["unfulfilled"][0]["quantity_short"], 6)

    def test_out_of_radius_pharmacy_is_ignored(self):
        tripoli = make_pharmacy("Tripoli Pharmacy", "Tripoli", (34.4367, 35.8497))
        create_inventory_batch(
            user=self.hamra_owner,
            pharmacy=tripoli,
            data={"medicine": self.panadol, "initial_quantity": 50, "selling_price": self.panadol.regulated_price, "batch_number": "T-1"},
        )

        plan = self.quote([{"medicine": str(self.panadol.id), "quantity": 2}])

        self.assertEqual(plan["allocations"], [])


class ReservationTests(SourcingTestCase):
    def test_placing_an_order_holds_stock_against_the_batch(self):
        batch = self.stock(self.hamra, self.panadol, 10)

        place_order(customer=self.shopper, items=[{"medicine": str(self.panadol.id), "quantity": 4}], address=self.address)
        batch.refresh_from_db()

        self.assertEqual(batch.current_quantity, 10, "reserving must not deduct stock; the box is still on the shelf")
        self.assertEqual(batch.reserved_quantity, 4)
        self.assertEqual(batch.available_quantity, 6)

    def test_reserved_stock_is_invisible_to_the_next_shopper(self):
        self.stock(self.hamra, self.panadol, 5)
        place_order(customer=self.shopper, items=[{"medicine": str(self.panadol.id), "quantity": 5}], address=self.address)

        plan = self.quote([{"medicine": str(self.panadol.id), "quantity": 2}])

        self.assertEqual(plan["allocations"], [])

    def test_reservation_uses_earliest_expiry_first(self):
        soon = create_inventory_batch(
            user=self.hamra_owner,
            pharmacy=self.hamra,
            data={
                "medicine": self.panadol,
                "batch_number": "EXPIRES-SOON",
                "initial_quantity": 3,
                "expiry_date": timezone.localdate() + timezone.timedelta(days=20),
                "selling_price": self.panadol.regulated_price,
            },
        )
        later = create_inventory_batch(
            user=self.hamra_owner,
            pharmacy=self.hamra,
            data={
                "medicine": self.panadol,
                "batch_number": "EXPIRES-LATER",
                "initial_quantity": 10,
                "expiry_date": timezone.localdate() + timezone.timedelta(days=300),
                "selling_price": self.panadol.regulated_price,
            },
        )

        place_order(customer=self.shopper, items=[{"medicine": str(self.panadol.id), "quantity": 4}], address=self.address)
        soon.refresh_from_db()
        later.refresh_from_db()

        self.assertEqual(soon.reserved_quantity, 3, "the batch expiring first should be consumed first")
        self.assertEqual(later.reserved_quantity, 1)

    def test_rejecting_a_slice_returns_the_held_stock(self):
        batch = self.stock(self.hamra, self.panadol, 10)
        order = place_order(customer=self.shopper, items=[{"medicine": str(self.panadol.id), "quantity": 4}], address=self.address)

        reject_fulfillment(fulfillment=order.fulfillments.first(), user=self.hamra_owner, reason="Out of stock on the shelf")
        batch.refresh_from_db()
        order.refresh_from_db()

        self.assertEqual(batch.reserved_quantity, 0)
        self.assertEqual(batch.current_quantity, 10)
        self.assertEqual(order.status, Order.Status.CANCELLED)

    def test_handover_converts_the_hold_into_a_real_deduction_and_invoice(self):
        batch = self.stock(self.hamra, self.panadol, 10)
        order = place_order(customer=self.shopper, items=[{"medicine": str(self.panadol.id), "quantity": 4}], address=self.address)
        fulfillment = order.fulfillments.first()
        from apps.orders.services.lifecycle import accept_fulfillment

        accept_fulfillment(fulfillment=fulfillment, user=self.hamra_owner)

        hand_over(fulfillment=fulfillment, user=self.hamra_owner, handover_code=fulfillment.handover_code)
        batch.refresh_from_db()
        fulfillment.refresh_from_db()

        self.assertEqual(batch.current_quantity, 6, "stock leaves the shelf at handover")
        self.assertEqual(batch.reserved_quantity, 0)
        self.assertIsNotNone(fulfillment.sale)
        self.assertEqual(fulfillment.sale.total, Decimal("9.00"))  # 4 x 2.25 MoPH price

    def test_wrong_handover_code_is_refused(self):
        self.stock(self.hamra, self.panadol, 10)
        order = place_order(customer=self.shopper, items=[{"medicine": str(self.panadol.id), "quantity": 2}], address=self.address)
        fulfillment = order.fulfillments.first()
        from apps.orders.services.lifecycle import FulfillmentError, accept_fulfillment

        accept_fulfillment(fulfillment=fulfillment, user=self.hamra_owner)

        with self.assertRaises(FulfillmentError):
            hand_over(fulfillment=fulfillment, user=self.hamra_owner, handover_code="000000")

    def test_stale_reservations_are_released_so_stock_is_not_stranded(self):
        batch = self.stock(self.hamra, self.panadol, 10)
        place_order(customer=self.shopper, items=[{"medicine": str(self.panadol.id), "quantity": 4}], address=self.address)
        StockReservation.objects.update(expires_at=timezone.now() - timezone.timedelta(minutes=1))

        released = expire_stale_reservations()
        batch.refresh_from_db()

        self.assertEqual(released, 1)
        self.assertEqual(batch.reserved_quantity, 0)

    def test_a_stock_hold_expiring_moves_the_pending_order_out_of_limbo(self):
        self.stock(self.hamra, self.panadol, 10)
        order = place_order(customer=self.shopper, items=[{"medicine": str(self.panadol.id), "quantity": 4}], address=self.address)
        StockReservation.objects.update(expires_at=timezone.now() - timezone.timedelta(minutes=1))

        expire_stale_reservations()
        order.refresh_from_db()
        fulfillment = order.fulfillments.first()
        fulfillment.refresh_from_db()

        self.assertEqual(fulfillment.status, OrderFulfillment.Status.EXPIRED)
        self.assertEqual(order.status, Order.Status.CANCELLED)

    def test_a_pharmacy_cannot_accept_a_slice_whose_hold_already_lapsed(self):
        from apps.orders.services.lifecycle import FulfillmentError, accept_fulfillment

        self.stock(self.hamra, self.panadol, 10)
        order = place_order(customer=self.shopper, items=[{"medicine": str(self.panadol.id), "quantity": 4}], address=self.address)
        fulfillment = order.fulfillments.first()
        # Simulate the race: the hold has lapsed but the sweep hasn't run yet, so the
        # fulfillment is still nominally PENDING.
        StockReservation.objects.update(expires_at=timezone.now() - timezone.timedelta(minutes=1))

        with self.assertRaises(FulfillmentError):
            accept_fulfillment(fulfillment=fulfillment, user=self.hamra_owner)


class IdempotentOrderPlacementTests(SourcingTestCase):
    def test_repeating_the_same_idempotency_key_returns_the_original_order(self):
        self.stock(self.hamra, self.panadol, 10)

        first = place_order(
            customer=self.shopper, items=[{"medicine": str(self.panadol.id), "quantity": 2}], address=self.address, idempotency_key="basket-abc123"
        )
        second = place_order(
            customer=self.shopper, items=[{"medicine": str(self.panadol.id), "quantity": 2}], address=self.address, idempotency_key="basket-abc123"
        )

        self.assertEqual(first.id, second.id)
        self.assertEqual(Order.objects.filter(customer=self.shopper).count(), 1)

    def test_a_different_key_places_a_separate_order(self):
        self.stock(self.hamra, self.panadol, 10)

        first = place_order(
            customer=self.shopper, items=[{"medicine": str(self.panadol.id), "quantity": 2}], address=self.address, idempotency_key="key-1"
        )
        second = place_order(
            customer=self.shopper, items=[{"medicine": str(self.panadol.id), "quantity": 2}], address=self.address, idempotency_key="key-2"
        )

        self.assertNotEqual(first.id, second.id)


class ReviewModerationTests(SourcingTestCase):
    def _delivered_order(self):
        from apps.orders.services.lifecycle import accept_fulfillment, hand_over

        self.stock(self.hamra, self.panadol, 10)
        order = place_order(customer=self.shopper, items=[{"medicine": str(self.panadol.id), "quantity": 2}], address=self.address)
        fulfillment = order.fulfillments.first()
        accept_fulfillment(fulfillment=fulfillment, user=self.hamra_owner)
        hand_over(fulfillment=fulfillment, user=self.hamra_owner, handover_code=fulfillment.handover_code, collected_in_store=True)
        order.refresh_from_db()
        return order

    def test_hiding_a_review_removes_it_from_the_pharmacy_rating(self):
        from apps.orders.services.lifecycle import set_review_visibility, submit_review

        order = self._delivered_order()
        review = submit_review(order=order, pharmacy=self.hamra, customer=self.shopper, rating=1, comment="Bad experience")
        self.hamra.refresh_from_db()
        self.assertEqual(self.hamra.rating_count, 1)

        set_review_visibility(review=review, is_hidden=True, reason="Abusive language")
        self.hamra.refresh_from_db()

        self.assertEqual(self.hamra.rating_count, 0)


class UnmetDemandTests(SourcingTestCase):
    def test_a_basket_nobody_can_fill_is_recorded_as_demand(self):
        with self.assertRaises(OrderError):
            place_order(customer=self.shopper, items=[{"medicine": str(self.panadol.id), "quantity": 2}], address=self.address)

        signal = UnmetDemandSignal.objects.get()
        self.assertEqual(signal.medicine_id, self.panadol.id)
        self.assertEqual(signal.area, "Hamra")
        self.assertEqual(signal.source, UnmetDemandSignal.Source.BASKET)

    def test_partial_shortfall_is_recorded_even_when_the_order_succeeds(self):
        self.stock(self.hamra, self.panadol, 2)

        place_order(customer=self.shopper, items=[{"medicine": str(self.panadol.id), "quantity": 5}], address=self.address)

        signal = UnmetDemandSignal.objects.get()
        self.assertEqual(signal.quantity_requested, 3)


class ScheduledOrderTests(SourcingTestCase):
    def test_scheduled_order_waits_out_of_the_dispatch_pool(self):
        self.stock(self.hamra, self.panadol, 10)
        target = timezone.now() + timezone.timedelta(hours=6)

        order = place_order(
            customer=self.shopper,
            items=[{"medicine": str(self.panadol.id), "quantity": 2}],
            address=self.address,
            scheduled_for=target,
        )

        self.assertEqual(order.status, Order.Status.SCHEDULED)
        self.assertIsNone(order.released_at)
        self.assertEqual(order.scheduled_for, target)

    def test_scheduled_order_joins_the_pool_near_its_window(self):
        from apps.orders.services.schedule import release_due_scheduled_orders

        self.stock(self.hamra, self.panadol, 10)
        order = place_order(
            customer=self.shopper,
            items=[{"medicine": str(self.panadol.id), "quantity": 2}],
            address=self.address,
            scheduled_for=timezone.now() + timezone.timedelta(minutes=30),
        )

        released = release_due_scheduled_orders()
        order.refresh_from_db()

        self.assertEqual(released, [order.reference])
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertIsNotNone(order.released_at)

    def test_a_time_in_the_past_is_refused(self):
        self.stock(self.hamra, self.panadol, 10)

        with self.assertRaises(OrderError):
            place_order(
                customer=self.shopper,
                items=[{"medicine": str(self.panadol.id), "quantity": 2}],
                address=self.address,
                scheduled_for=timezone.now() - timezone.timedelta(hours=1),
            )


class NonMarketedMedicineTests(SourcingTestCase):
    def test_non_marketed_item_cannot_be_ordered(self):
        self.panadol.market_status = MarketStatus.NON_MARKETED
        self.panadol.save(update_fields=["market_status"])
        self.stock(self.hamra, self.panadol, 10)

        with self.assertRaises(OrderError):
            place_order(customer=self.shopper, items=[{"medicine": str(self.panadol.id), "quantity": 1}], address=self.address)

    def test_marketed_item_is_unaffected(self):
        self.stock(self.hamra, self.panadol, 10)

        order = place_order(customer=self.shopper, items=[{"medicine": str(self.panadol.id), "quantity": 1}], address=self.address)

        self.assertEqual(order.status, Order.Status.PENDING)


class PrescriptionRequirementTests(SourcingTestCase):
    def setUp(self):
        super().setUp()
        from apps.eprescriptions.models import Doctor
        from apps.eprescriptions.services.issue import issue_prescription

        self.nexium.requires_prescription = True
        self.nexium.save(update_fields=["requires_prescription"])
        self.stock(self.hamra, self.nexium, 10)
        self.doctor = Doctor.objects.create(license_number="LB-MD-9", full_name="Rima Khalil", email="doc@doctors.test", is_active=True)
        doctor_user = self.shopper.__class__.objects.create_user(email="doc@doctors.test", password="Password123!", role=UserRole.DOCTOR)
        self.doctor.user = doctor_user
        self.doctor.is_activated = True
        self.doctor.activated_at = timezone.now()
        self.doctor.save()
        self.issue_prescription = issue_prescription

    def test_prescription_required_item_is_refused_without_one(self):
        with self.assertRaises(OrderError):
            place_order(customer=self.shopper, items=[{"medicine": str(self.nexium.id), "quantity": 1}], address=self.address)

    def test_prescription_required_item_succeeds_with_a_covering_prescription(self):
        prescription, _secret, _pin = self.issue_prescription(
            doctor=self.doctor, patient={"patient_name": "Shopper"}, items=[{"medicine": str(self.nexium.id), "quantity_prescribed": 3}]
        )

        order = place_order(
            customer=self.shopper, items=[{"medicine": str(self.nexium.id), "quantity": 2}], address=self.address, prescription=prescription
        )

        self.assertEqual(order.status, Order.Status.PENDING)

    def test_prescription_with_insufficient_remaining_quantity_is_refused(self):
        prescription, _secret, _pin = self.issue_prescription(
            doctor=self.doctor, patient={"patient_name": "Shopper"}, items=[{"medicine": str(self.nexium.id), "quantity_prescribed": 1}]
        )

        with self.assertRaises(OrderError):
            place_order(
                customer=self.shopper, items=[{"medicine": str(self.nexium.id), "quantity": 2}], address=self.address, prescription=prescription
            )

    def test_placing_an_order_consumes_the_prescription_so_it_cannot_be_redeemed_twice(self):
        """
        Before this, place_order only validated quantity_remaining, it never claimed it - a
        shopper could order online and still walk into a pharmacy and redeem the same units.
        """
        from apps.eprescriptions.models import Prescription

        prescription, _secret, _pin = self.issue_prescription(
            doctor=self.doctor, patient={"patient_name": "Shopper"}, items=[{"medicine": str(self.nexium.id), "quantity_prescribed": 3}]
        )

        place_order(
            customer=self.shopper, items=[{"medicine": str(self.nexium.id), "quantity": 2}], address=self.address, prescription=prescription
        )

        prescription.refresh_from_db()
        item = prescription.items.get()
        self.assertEqual(item.quantity_dispensed, 2)
        self.assertEqual(item.quantity_remaining, 1)
        self.assertEqual(prescription.status, Prescription.Status.PARTIALLY_DISPENSED)
        self.assertEqual(prescription.dispenses.count(), 1)
        self.assertEqual(prescription.dispenses.get().pharmacy_id, self.hamra.id)

        # Only 1 unit left - a second order for 2 must be refused, not silently over-redeemed.
        with self.assertRaises(OrderError):
            place_order(
                customer=self.shopper, items=[{"medicine": str(self.nexium.id), "quantity": 2}], address=self.address, prescription=prescription
            )


class ConnectorFreshnessSourcingTests(SourcingTestCase):
    """
    Sourcing should not trust a connector-fed pharmacy's stock as much once its last POS
    observation is old - a pharmacy whose connector has gone quiet can still show units
    that sold out on the shelf hours ago.
    """

    def test_a_stale_connector_can_lose_a_basket_it_would_otherwise_win_on_distance(self):
        # Hamra is far nearer to the shopper than Achrafieh (see distances above), so it
        # wins on cost alone. A very stale POS observation should be enough to flip that.
        self.stock(self.hamra, self.panadol, 20)
        self.stock(self.achrafieh, self.panadol, 20)

        fresh_plan = self.quote([{"medicine": str(self.panadol.id), "quantity": 2}])
        self.assertEqual(fresh_plan["allocations"][0]["pharmacy"], self.hamra.id, "sanity check: nearer pharmacy wins when both are equally fresh")

        InventoryBatch.objects.filter(pharmacy=self.hamra, medicine=self.panadol).update(
            last_pos_observed_at=timezone.now() - timezone.timedelta(hours=200)
        )

        stale_plan = self.quote([{"medicine": str(self.panadol.id), "quantity": 2}])
        self.assertEqual(stale_plan["allocations"][0]["pharmacy"], self.achrafieh.id, "a connector dead for days should lose to a fresher, farther pharmacy")

    def test_freshness_within_the_grace_window_is_not_penalised(self):
        self.stock(self.hamra, self.panadol, 20)
        self.stock(self.achrafieh, self.panadol, 20)
        InventoryBatch.objects.filter(pharmacy=self.hamra, medicine=self.panadol).update(last_pos_observed_at=timezone.now() - timezone.timedelta(hours=1))

        plan = self.quote([{"medicine": str(self.panadol.id), "quantity": 2}])

        self.assertEqual(plan["allocations"][0]["pharmacy"], self.hamra.id, "a sync from an hour ago is live, not stale - the nearer pharmacy should still win")

    def test_dashboard_managed_stock_with_no_observation_is_never_penalised(self):
        # Never-synced batches have last_pos_observed_at = None; that must read as "live",
        # not as maximally stale, or every dashboard-only pharmacy would rank last.
        self.stock(self.hamra, self.panadol, 20)
        self.stock(self.achrafieh, self.panadol, 20)

        plan = self.quote([{"medicine": str(self.panadol.id), "quantity": 2}])

        self.assertEqual(plan["allocations"][0]["pharmacy"], self.hamra.id)
