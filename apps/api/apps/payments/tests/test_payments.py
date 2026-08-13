"""
What must hold:
  - placing an order always creates exactly one payment, matching the order's total
  - cash on delivery starts PENDING and does not touch a gateway
  - the mock gateway charges synchronously and marks the order paid immediately
  - cash on delivery only settles once the order is actually delivered/collected
  - a shopper cannot pay for, or see, another shopper's order
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import UserRole
from apps.inventory.services.stock import create_inventory_batch
from apps.medicines.models import Medicine
from apps.orders.services.lifecycle import accept_fulfillment, hand_over
from apps.orders.services.placement import place_order
from apps.payments.models import Payment
from apps.pharmacies.models import Pharmacy

HAMRA = (33.8975, 35.4790)
SHOPPER_HOME = (33.8991, 35.4772)


class PaymentFlowTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.pharmacy = Pharmacy.objects.create(
            name="Cedar Care", area="Hamra", city="Beirut", address="Hamra street", phone="+961-1-000-000",
            latitude=Decimal(str(HAMRA[0])), longitude=Decimal(str(HAMRA[1])),
        )
        self.owner = User.objects.create_user(email="owner@hamra.test", password="Password123!", role=UserRole.PHARMACY_OWNER, pharmacy=self.pharmacy)
        self.shopper = User.objects.create_user(email="shopper@test.test", password="Password123!", role=UserRole.CUSTOMER)
        self.other_shopper = User.objects.create_user(email="other@test.test", password="Password123!", role=UserRole.CUSTOMER)
        self.medicine = Medicine.objects.create(brand_name="Panadol", strength="500mg", form="Tablet", regulated_price=Decimal("2.25"))
        create_inventory_batch(
            user=self.owner,
            pharmacy=self.pharmacy,
            data={
                "medicine": self.medicine,
                "initial_quantity": 20,
                "expiry_date": timezone.localdate() + timezone.timedelta(days=200),
                "purchase_cost": Decimal("1.00"),
                "selling_price": Decimal("2.25"),
            },
        )
        self.address = self.shopper.addresses.create(
            label="Home", contact_name="Shopper", phone="+961-71-000-000", address="Hamra", area="Hamra", city="Beirut",
            latitude=Decimal(str(SHOPPER_HOME[0])), longitude=Decimal(str(SHOPPER_HOME[1])), is_default=True,
        )

    def place(self, payment_method=Payment.Provider.CASH_ON_DELIVERY):
        return place_order(
            customer=self.shopper,
            items=[{"medicine": str(self.medicine.id), "quantity": 2}],
            address=self.address,
            payment_method=payment_method,
        )

    def test_placing_an_order_creates_a_pending_cod_payment_by_default(self):
        order = self.place()
        self.assertEqual(order.payment.provider, Payment.Provider.CASH_ON_DELIVERY)
        self.assertEqual(order.payment.status, Payment.Status.PENDING)
        self.assertEqual(order.payment.amount, order.total)

    def test_mock_gateway_charges_synchronously(self):
        order = self.place(payment_method=Payment.Provider.MOCK_GATEWAY)
        self.assertEqual(order.payment.status, Payment.Status.PAID)
        self.assertTrue(order.payment.external_reference.startswith("MOCK-"))
        self.assertIsNotNone(order.payment.paid_at)

    def test_cod_settles_only_once_the_order_is_fully_delivered(self):
        order = self.place()
        fulfillment = order.fulfillments.get()
        accept_fulfillment(fulfillment=fulfillment, user=self.owner)
        order.payment.refresh_from_db()
        self.assertEqual(order.payment.status, Payment.Status.PENDING)

        hand_over(fulfillment=fulfillment, user=self.owner, handover_code=fulfillment.handover_code, collected_in_store=True)
        order.payment.refresh_from_db()
        self.assertEqual(order.payment.status, Payment.Status.PAID)
        self.assertIsNotNone(order.payment.paid_at)


class PaymentApiTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.pharmacy = Pharmacy.objects.create(
            name="Cedar Care", area="Hamra", city="Beirut", address="Hamra street", phone="+961-1-000-000",
            latitude=Decimal(str(HAMRA[0])), longitude=Decimal(str(HAMRA[1])),
        )
        self.owner = User.objects.create_user(email="owner@hamra.test", password="Password123!", role=UserRole.PHARMACY_OWNER, pharmacy=self.pharmacy)
        self.shopper = User.objects.create_user(email="shopper@test.test", password="Password123!", role=UserRole.CUSTOMER)
        self.other_shopper = User.objects.create_user(email="other@test.test", password="Password123!", role=UserRole.CUSTOMER)
        self.medicine = Medicine.objects.create(brand_name="Panadol", strength="500mg", form="Tablet", regulated_price=Decimal("2.25"))
        create_inventory_batch(
            user=self.owner,
            pharmacy=self.pharmacy,
            data={
                "medicine": self.medicine,
                "initial_quantity": 20,
                "expiry_date": timezone.localdate() + timezone.timedelta(days=200),
                "purchase_cost": Decimal("1.00"),
                "selling_price": Decimal("2.25"),
            },
        )
        self.address = self.shopper.addresses.create(
            label="Home", contact_name="Shopper", phone="+961-71-000-000", address="Hamra", area="Hamra", city="Beirut",
            latitude=Decimal(str(SHOPPER_HOME[0])), longitude=Decimal(str(SHOPPER_HOME[1])), is_default=True,
        )
        self.order = place_order(
            customer=self.shopper,
            items=[{"medicine": str(self.medicine.id), "quantity": 2}],
            address=self.address,
            payment_method=Payment.Provider.CASH_ON_DELIVERY,
        )

    def test_payment_methods_endpoint_is_public(self):
        response = self.client.get("/api/shop/payment-methods/")
        self.assertEqual(response.status_code, 200)
        codes = {entry["code"] for entry in response.data}
        self.assertEqual(codes, {Payment.Provider.CASH_ON_DELIVERY, Payment.Provider.MOCK_GATEWAY})

    def test_cannot_pay_for_someone_elses_order(self):
        self.client.force_authenticate(self.other_shopper)
        response = self.client.post(f"/api/shop/orders/{self.order.id}/pay/")
        self.assertEqual(response.status_code, 404)

    def test_cod_order_cannot_be_charged_online(self):
        self.client.force_authenticate(self.shopper)
        response = self.client.post(f"/api/shop/orders/{self.order.id}/pay/")
        self.assertEqual(response.status_code, 400)
