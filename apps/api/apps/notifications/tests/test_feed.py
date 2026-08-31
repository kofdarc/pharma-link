"""
The computed notification feed (apps.notifications.services.feed_for).

Checks the mechanics that matter: the right role sees the right items, the ids are
stable and state-encoding, and one user's feed never reaches into another's records.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import UserRole
from apps.inventory.services.stock import create_inventory_batch
from apps.medicines.models import Medicine
from apps.notifications.services import feed_for
from apps.orders.models import Order
from apps.orders.services.lifecycle import accept_fulfillment
from apps.orders.services.placement import place_order
from apps.payments.models import Payment
from apps.pharmacies.models import Pharmacy, PharmacyApplication

HAMRA = (Decimal("33.8975"), Decimal("35.4790"))
SHOPPER_HOME = (Decimal("33.8991"), Decimal("35.4772"))


class FeedTestCase(TestCase):
    def setUp(self):
        User = get_user_model()
        self.pharmacy = Pharmacy.objects.create(
            name="Cedar Care", area="Hamra", city="Beirut", address="Hamra street", phone="+961-1-000-000",
            latitude=HAMRA[0], longitude=HAMRA[1],
        )
        self.owner = User.objects.create_user(
            email="owner@hamra.test", password="Password123!", role=UserRole.PHARMACY_OWNER, pharmacy=self.pharmacy
        )
        self.other_owner = User.objects.create_user(
            email="owner@other.test", password="Password123!", role=UserRole.PHARMACY_OWNER,
            pharmacy=Pharmacy.objects.create(
                name="Bliss", area="Hamra", city="Beirut", address="Bliss street", phone="+961-1-111-111",
                latitude=HAMRA[0], longitude=HAMRA[1],
            ),
        )
        self.shopper = User.objects.create_user(email="shopper@test.test", password="Password123!", role=UserRole.CUSTOMER)
        self.admin = User.objects.create_user(email="admin@test.test", password="Password123!", role=UserRole.PLATFORM_ADMIN)
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
            latitude=SHOPPER_HOME[0], longitude=SHOPPER_HOME[1], is_default=True,
        )

    def _place_order(self):
        return place_order(
            customer=self.shopper,
            items=[{"medicine": str(self.medicine.id), "quantity": 2}],
            address=self.address,
            payment_method=Payment.Provider.CASH_ON_DELIVERY,
        )

    def test_pharmacy_sees_incoming_order_and_not_another_pharmacys(self):
        self._place_order()

        feed = feed_for(self.owner)
        kinds = {item["kind"] for item in feed}
        self.assertIn("incoming_order", kinds)
        self.assertTrue(all(item["id"].startswith(("incoming-order:", "rx-upload:", "stock-")) for item in feed))
        self.assertEqual(feed_for(self.other_owner), [])

    def test_customer_sees_order_status_and_id_encodes_state(self):
        order = self._place_order()
        fulfillment = order.fulfillments.first()
        accept_fulfillment(fulfillment=fulfillment, user=self.owner)
        fulfillment.refresh_from_db()

        feed = feed_for(self.shopper)
        order_items = [item for item in feed if item["kind"] == "order"]
        self.assertEqual(len(order_items), 1)
        self.assertEqual(order_items[0]["id"], f"order:{fulfillment.id}:ACCEPTED")
        self.assertEqual(order_items[0]["params"]["reference"], order.reference)
        self.assertEqual(order_items[0]["href"], f"/orders/{order.id}")

    def test_customer_feed_is_scoped_to_own_orders(self):
        self._place_order()
        stranger = get_user_model().objects.create_user(
            email="stranger@test.test", password="Password123!", role=UserRole.CUSTOMER
        )
        self.assertEqual(feed_for(stranger), [])

    def test_admin_sees_pending_application_only(self):
        PharmacyApplication.objects.create(
            pharmacy_name="New Pharmacy", owner_name="A Owner", email="new@pharm.test", phone="+961-1-222-222",
            area="Achrafieh", status=PharmacyApplication.Status.PENDING,
        )
        PharmacyApplication.objects.create(
            pharmacy_name="Approved One", owner_name="B Owner", email="b@pharm.test", phone="+961-1-333-333",
            status=PharmacyApplication.Status.APPROVED,
        )
        feed = feed_for(self.admin)
        application_items = [item for item in feed if item["kind"] == "application"]
        self.assertEqual(len(application_items), 1)
        self.assertEqual(application_items[0]["params"]["pharmacy_name"], "New Pharmacy")

    def test_unknown_role_gets_empty_feed(self):
        self.shopper.role = "SOMETHING_ELSE"
        self.assertEqual(feed_for(self.shopper), [])

    def test_endpoint_requires_auth_and_returns_feed_shape(self):
        client = APIClient()
        self.assertEqual(client.get("/api/notifications/").status_code, 401)

        self._place_order()
        client.force_authenticate(self.owner)
        response = client.get("/api/notifications/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("notifications", response.data)
        self.assertIn("generated_at", response.data)
        self.assertTrue(any(item["kind"] == "incoming_order" for item in response.data["notifications"]))
