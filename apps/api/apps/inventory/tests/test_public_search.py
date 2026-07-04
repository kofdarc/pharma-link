from decimal import Decimal
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import UserRole
from apps.inventory.services.stock import create_inventory_batch
from apps.medicines.models import Medicine, MedicineAlias
from apps.pharmacies.models import Pharmacy


class PublicAvailabilityTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        pharmacy = Pharmacy.objects.create(name="Cedar Care", city="Beirut", area="Hamra", phone="111", is_public=True, is_active=True)
        user = User.objects.create_user(email="staff@test.local", password="Password123!", role=UserRole.PHARMACY_STAFF, pharmacy=pharmacy)
        medicine = Medicine.objects.create(brand_name="Panadol", generic_name="Paracetamol", strength="500mg", form="Tablet")
        MedicineAlias.objects.create(medicine=medicine, alias="Acetaminophen")
        create_inventory_batch(
            user=user,
            pharmacy=pharmacy,
            data={
                "medicine": medicine,
                "initial_quantity": 3,
                "selling_price": Decimal("2.25"),
                "low_stock_threshold": 5,
                "expiry_date": timezone.localdate() + timedelta(days=90),
            },
        )

    def test_public_search_hides_exact_stock_quantity(self):
        response = self.client.get("/api/public/search/?q=acetaminophen")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]["availability_status"], "Low stock")
        self.assertNotIn("quantity", str(response.data).lower())
        self.assertIn("confirm", response.data[0]["disclaimer"].lower())

