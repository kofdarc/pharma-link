from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.accounts.models import UserRole
from apps.inventory.services.stock import create_inventory_batch
from apps.medicines.models import Medicine, PriceRegime
from apps.pharmacies.models import Pharmacy


class PermissionBoundaryTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.pharmacy_a = Pharmacy.objects.create(name="Alpha Pharmacy", city="Beirut", area="Hamra", phone="111")
        self.pharmacy_b = Pharmacy.objects.create(name="Beta Pharmacy", city="Beirut", area="Achrafieh", phone="222")
        self.admin = User.objects.create_user(email="admin@test.local", password="Password123!", role=UserRole.PLATFORM_ADMIN)
        self.staff_a = User.objects.create_user(email="staff-a@test.local", password="Password123!", role=UserRole.PHARMACY_STAFF, pharmacy=self.pharmacy_a)
        self.staff_b = User.objects.create_user(email="staff-b@test.local", password="Password123!", role=UserRole.PHARMACY_STAFF, pharmacy=self.pharmacy_b)
        self.medicine = Medicine.objects.create(
            brand_name="Panadol",
            generic_name="Paracetamol",
            strength="500mg",
            form="Tablet",
            price_regime=PriceRegime.FREE,
        )
        self.batch_b = create_inventory_batch(
            user=self.staff_b,
            pharmacy=self.pharmacy_b,
            data={"medicine": self.medicine, "initial_quantity": 10, "selling_price": Decimal("2.00")},
        )

    def test_staff_cannot_access_admin_pharmacy_api(self):
        self.client.force_authenticate(self.staff_a)
        response = self.client.get("/api/admin/pharmacies/")
        self.assertEqual(response.status_code, 403)

    def test_admin_can_access_admin_pharmacy_api(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/admin/pharmacies/")
        self.assertEqual(response.status_code, 200)

    def test_staff_cannot_read_other_pharmacy_inventory_batch(self):
        self.client.force_authenticate(self.staff_a)
        response = self.client.get(f"/api/pharmacy/inventory/{self.batch_b.id}/")
        self.assertEqual(response.status_code, 404)
