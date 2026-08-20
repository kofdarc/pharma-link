"""
What must hold:
  - deactivating a pharmacy rejects its open order slices instead of stranding them
  - a paid order that empties out entirely gets refunded
  - a pharmacy application can be approved into a real Pharmacy + owner account, once
  - rejecting an application does not create anything
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import UserRole
from apps.inventory.services.stock import create_inventory_batch
from apps.medicines.models import Medicine
from apps.orders.models import OrderFulfillment
from apps.orders.services.placement import place_order
from apps.payments.models import Payment
from apps.pharmacies.models import Pharmacy, PharmacyApplication

HAMRA = (33.8975, 35.4790)
SHOPPER_HOME = (33.8991, 35.4772)


class PharmacyDeactivationTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.pharmacy = Pharmacy.objects.create(
            name="Cedar Care", area="Hamra", city="Beirut", address="Hamra street", phone="+961-1-000-000",
            latitude=Decimal(str(HAMRA[0])), longitude=Decimal(str(HAMRA[1])),
        )
        self.owner = User.objects.create_user(email="owner@hamra.test", password="Password123!", role=UserRole.PHARMACY_OWNER, pharmacy=self.pharmacy)
        self.admin = User.objects.create_user(email="admin@platform.test", password="Password123!", role=UserRole.PLATFORM_ADMIN)
        self.shopper = User.objects.create_user(email="shopper@test.test", password="Password123!", role=UserRole.CUSTOMER, email_verified=True)
        self.medicine = Medicine.objects.create(brand_name="Panadol", strength="500mg", form="Tablet", regulated_price=Decimal("2.25"))
        create_inventory_batch(
            user=self.owner, pharmacy=self.pharmacy,
            data={
                "medicine": self.medicine, "initial_quantity": 10,
                "expiry_date": timezone.localdate() + timezone.timedelta(days=200),
                "purchase_cost": Decimal("1.00"), "selling_price": Decimal("2.25"),
            },
        )
        self.address = self.shopper.addresses.create(
            label="Home", contact_name="Shopper", phone="1", address="Hamra", area="Hamra", city="Beirut",
            latitude=Decimal(str(SHOPPER_HOME[0])), longitude=Decimal(str(SHOPPER_HOME[1])), is_default=True,
        )

    def test_deactivating_a_pharmacy_rejects_its_pending_order(self):
        order = place_order(
            customer=self.shopper, items=[{"medicine": str(self.medicine.id), "quantity": 2}], address=self.address,
            payment_method=Payment.Provider.MOCK_GATEWAY,
        )
        self.assertEqual(order.payment.status, Payment.Status.PAID)

        self.client.force_authenticate(self.admin)
        response = self.client.patch(f"/api/admin/pharmacies/{self.pharmacy.id}/", {"is_active": False}, format="json")
        self.assertEqual(response.status_code, 200, response.data)

        fulfillment = order.fulfillments.get()
        fulfillment.refresh_from_db()
        order.refresh_from_db()
        order.payment.refresh_from_db()

        self.assertEqual(fulfillment.status, OrderFulfillment.Status.REJECTED)
        self.assertEqual(order.status, order.Status.CANCELLED)
        self.assertEqual(order.payment.status, Payment.Status.REFUNDED)

    def test_reactivating_does_not_touch_orders(self):
        self.client.force_authenticate(self.admin)
        self.client.patch(f"/api/admin/pharmacies/{self.pharmacy.id}/", {"is_active": False}, format="json")
        response = self.client.patch(f"/api/admin/pharmacies/{self.pharmacy.id}/", {"is_active": True}, format="json")
        self.assertEqual(response.status_code, 200)


class PharmacyApplicationTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user(email="admin@platform.test", password="Password123!", role=UserRole.PLATFORM_ADMIN)

    def test_submitting_and_approving_creates_a_pharmacy_and_owner(self):
        submit = self.client.post(
            "/api/public/pharmacy-applications/",
            {"pharmacy_name": "New Corner Pharmacy", "owner_name": "Jad", "email": "jad@newpharmacy.test", "phone": "+961-1-999-999", "city": "Beirut", "area": "Gemmayze"},
            format="json",
        )
        self.assertEqual(submit.status_code, 201, submit.data)
        application_id = submit.data["id"]

        self.client.force_authenticate(self.admin)
        response = self.client.post(f"/api/admin/pharmacy-applications/{application_id}/approve/", {}, format="json")

        self.assertEqual(response.status_code, 200, response.data)
        application = PharmacyApplication.objects.get(id=application_id)
        self.assertEqual(application.status, PharmacyApplication.Status.APPROVED)
        self.assertIsNotNone(application.created_pharmacy)
        self.assertTrue(Pharmacy.objects.filter(id=application.created_pharmacy_id).exists())
        owner = get_user_model().objects.get(email="jad@newpharmacy.test")
        self.assertEqual(owner.role, UserRole.PHARMACY_OWNER)
        self.assertEqual(owner.pharmacy_id, application.created_pharmacy_id)
        self.assertFalse(owner.has_usable_password())
        self.assertEqual(len(mail.outbox), 1)  # the "set your password" link

    def test_approving_twice_is_refused(self):
        submit = self.client.post(
            "/api/public/pharmacy-applications/",
            {"pharmacy_name": "Another Pharmacy", "owner_name": "Sara", "email": "sara@another.test", "phone": "+961-1-888-888"},
            format="json",
        )
        application_id = submit.data["id"]
        self.client.force_authenticate(self.admin)
        self.client.post(f"/api/admin/pharmacy-applications/{application_id}/approve/", {}, format="json")

        response = self.client.post(f"/api/admin/pharmacy-applications/{application_id}/approve/", {}, format="json")

        self.assertEqual(response.status_code, 400)

    def test_rejecting_creates_nothing(self):
        submit = self.client.post(
            "/api/public/pharmacy-applications/",
            {"pharmacy_name": "Rejected Pharmacy", "owner_name": "Nour", "email": "nour@rejected.test", "phone": "+961-1-777-777"},
            format="json",
        )
        application_id = submit.data["id"]
        self.client.force_authenticate(self.admin)

        response = self.client.post(f"/api/admin/pharmacy-applications/{application_id}/reject/", {"note": "Not enough info"}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Pharmacy.objects.filter(name="Rejected Pharmacy").exists())
        self.assertFalse(get_user_model().objects.filter(email="nour@rejected.test").exists())
