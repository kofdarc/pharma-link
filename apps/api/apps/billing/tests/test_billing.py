"""
What must hold:
  - a pharmacy on a paid plan is charged a service fee when it accepts a platform request
  - a pharmacy with no subscription, or a zero-fee plan, is not charged
  - accepting the same fulfillment twice never double-charges
  - a pharmacy can only see its own service fees
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import UserRole
from apps.billing.models import PharmacySubscription, PlatformServiceFee, SubscriptionPlan
from apps.inventory.services.stock import create_inventory_batch
from apps.medicines.models import Medicine
from apps.orders.models import OrderFulfillment
from apps.orders.services.lifecycle import accept_fulfillment, reject_fulfillment
from apps.orders.services.placement import place_order
from apps.pharmacies.models import Pharmacy

HAMRA = (33.8975, 35.4790)
SHOPPER_HOME = (33.8991, 35.4772)


class ServiceFeeTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.pharmacy = Pharmacy.objects.create(
            name="Cedar Care", area="Hamra", city="Beirut", address="Hamra street", phone="+961-1-000-000",
            latitude=Decimal(str(HAMRA[0])), longitude=Decimal(str(HAMRA[1])),
        )
        self.unsubscribed_pharmacy = Pharmacy.objects.create(
            name="Achrafieh Health", area="Achrafieh", city="Beirut", address="Achrafieh street", phone="+961-1-000-001",
            latitude=Decimal(str(HAMRA[0])), longitude=Decimal(str(HAMRA[1])),
        )
        self.owner = User.objects.create_user(email="owner@hamra.test", password="Password123!", role=UserRole.PHARMACY_OWNER, pharmacy=self.pharmacy)
        self.unsubscribed_owner = User.objects.create_user(
            email="owner@ach.test", password="Password123!", role=UserRole.PHARMACY_OWNER, pharmacy=self.unsubscribed_pharmacy
        )
        self.shopper = User.objects.create_user(email="shopper@test.test", password="Password123!", role=UserRole.CUSTOMER)
        self.medicine = Medicine.objects.create(brand_name="Panadol", strength="500mg", form="Tablet", regulated_price=Decimal("2.25"))

        self.plan = SubscriptionPlan.objects.create(name="Growth", monthly_fee=Decimal("50.00"), service_fee_per_request=Decimal("1.50"))
        PharmacySubscription.objects.create(pharmacy=self.pharmacy, plan=self.plan)
        self.address = self.shopper.addresses.create(
            label="Home", contact_name="Shopper", phone="+961-71-000-000", address="Hamra", area="Hamra", city="Beirut",
            latitude=Decimal(str(SHOPPER_HOME[0])), longitude=Decimal(str(SHOPPER_HOME[1])), is_default=True,
        )

    def stock(self, pharmacy, owner):
        create_inventory_batch(
            user=owner,
            pharmacy=pharmacy,
            data={
                "medicine": self.medicine,
                "initial_quantity": 20,
                "expiry_date": timezone.localdate() + timezone.timedelta(days=200),
                "purchase_cost": Decimal("1.00"),
                "selling_price": Decimal("2.25"),
            },
        )

    def accept_order_at(self, pharmacy, owner):
        # Only `pharmacy` is stocked in each of these tests, so sourcing has exactly one
        # place to route the order to - which pharmacy gets picked is sourcing's job, not
        # billing's, and is already covered by apps.orders.tests.test_sourcing.
        self.stock(pharmacy, owner)
        order = place_order(customer=self.shopper, items=[{"medicine": str(self.medicine.id), "quantity": 1}], address=self.address)
        fulfillment = order.fulfillments.get(pharmacy=pharmacy)
        return accept_fulfillment(fulfillment=fulfillment, user=owner)

    def test_subscribed_pharmacy_is_charged_on_accept(self):
        fulfillment = self.accept_order_at(self.pharmacy, self.owner)
        fee = PlatformServiceFee.objects.get(fulfillment=fulfillment)
        self.assertEqual(fee.amount, Decimal("1.50"))
        self.assertEqual(fee.pharmacy, self.pharmacy)
        self.assertEqual(fee.status, PlatformServiceFee.Status.PENDING)

    def test_unsubscribed_pharmacy_is_not_charged(self):
        fulfillment = self.accept_order_at(self.unsubscribed_pharmacy, self.unsubscribed_owner)
        self.assertFalse(PlatformServiceFee.objects.filter(fulfillment=fulfillment).exists())

    def test_zero_fee_plan_does_not_charge(self):
        free_plan = SubscriptionPlan.objects.create(name="Starter", monthly_fee=Decimal("0"), service_fee_per_request=Decimal("0"))
        PharmacySubscription.objects.filter(pharmacy=self.pharmacy).update(plan=free_plan)
        fulfillment = self.accept_order_at(self.pharmacy, self.owner)
        self.assertFalse(PlatformServiceFee.objects.filter(fulfillment=fulfillment).exists())

    def test_accepting_twice_does_not_double_charge(self):
        self.stock(self.pharmacy, self.owner)
        order = place_order(customer=self.shopper, items=[{"medicine": str(self.medicine.id), "quantity": 1}], address=self.address)
        fulfillment = order.fulfillments.get(pharmacy=self.pharmacy)
        accept_fulfillment(fulfillment=fulfillment, user=self.owner)
        fulfillment.status = OrderFulfillment.Status.PENDING
        fulfillment.save(update_fields=["status"])
        accept_fulfillment(fulfillment=fulfillment, user=self.owner)
        self.assertEqual(PlatformServiceFee.objects.filter(fulfillment=fulfillment).count(), 1)

    def test_rejecting_an_already_accepted_fulfillment_waives_its_fee(self):
        fulfillment = self.accept_order_at(self.pharmacy, self.owner)
        fee = PlatformServiceFee.objects.get(fulfillment=fulfillment)
        self.assertEqual(fee.status, PlatformServiceFee.Status.PENDING)

        reject_fulfillment(fulfillment=fulfillment, user=self.owner, reason="Out of stock after all")

        fee.refresh_from_db()
        self.assertEqual(fee.status, PlatformServiceFee.Status.WAIVED)

    def test_rejecting_a_never_accepted_fulfillment_has_no_fee_to_waive(self):
        self.stock(self.pharmacy, self.owner)
        order = place_order(customer=self.shopper, items=[{"medicine": str(self.medicine.id), "quantity": 1}], address=self.address)
        fulfillment = order.fulfillments.get(pharmacy=self.pharmacy)

        reject_fulfillment(fulfillment=fulfillment, user=self.owner, reason="Can't fulfill")

        self.assertFalse(PlatformServiceFee.objects.filter(fulfillment=fulfillment).exists())


class ServiceFeeApiTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.pharmacy = Pharmacy.objects.create(name="Cedar Care", area="Hamra", city="Beirut", phone="+961-1-000-000")
        self.other_pharmacy = Pharmacy.objects.create(name="Achrafieh Health", area="Achrafieh", city="Beirut", phone="+961-1-000-001")
        self.owner = User.objects.create_user(email="owner@hamra.test", password="Password123!", role=UserRole.PHARMACY_OWNER, pharmacy=self.pharmacy)
        self.other_owner = User.objects.create_user(email="owner@ach.test", password="Password123!", role=UserRole.PHARMACY_OWNER, pharmacy=self.other_pharmacy)
        plan = SubscriptionPlan.objects.create(name="Growth", monthly_fee=Decimal("50.00"), service_fee_per_request=Decimal("1.50"))
        subscription = PharmacySubscription.objects.create(pharmacy=self.pharmacy, plan=plan)
        PharmacySubscription.objects.create(pharmacy=self.other_pharmacy, plan=plan)

        from apps.orders.models import DeliveryAddress, Order, OrderFulfillment as OF

        self.customer = User.objects.create_user(email="shopper@test.test", password="Password123!", role=UserRole.CUSTOMER)
        address = DeliveryAddress.objects.create(
            user=self.customer, contact_name="Shopper", phone="1", address="A", area="Hamra", city="Beirut", latitude=Decimal("33.9"), longitude=Decimal("35.5")
        )
        order = Order.objects.create(reference="MO-TEST-00001", customer=self.customer, contact_name="Shopper", contact_phone="1")
        fulfillment = OF.objects.create(order=order, pharmacy=self.pharmacy, subtotal=Decimal("10.00"), handover_code="123456")
        self.fee = PlatformServiceFee.objects.create(pharmacy=self.pharmacy, fulfillment=fulfillment, amount=Decimal("1.50"))
        self.subscription = subscription

    def test_pharmacy_only_sees_its_own_service_fees(self):
        self.client.force_authenticate(self.owner)
        response = self.client.get("/api/pharmacy/service-fees/")
        self.assertEqual(response.status_code, 200)
        ids = [row["id"] for row in response.data["results"]]
        self.assertEqual(ids, [str(self.fee.id)])

        self.client.force_authenticate(self.other_owner)
        response = self.client.get("/api/pharmacy/service-fees/")
        self.assertEqual(response.data["results"], [])

    def test_pharmacy_can_view_its_own_subscription(self):
        self.client.force_authenticate(self.owner)
        response = self.client.get("/api/pharmacy/subscription/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], str(self.subscription.id))
