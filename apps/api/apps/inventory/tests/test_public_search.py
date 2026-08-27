from decimal import Decimal
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import UserRole
from apps.inventory.services.stock import create_inventory_batch
from apps.medicines.models import Medicine, MedicineAlias, PriceRegime
from apps.pharmacies.models import Pharmacy


class PublicAvailabilityTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        pharmacy = Pharmacy.objects.create(name="Cedar Care", city="Beirut", area="Hamra", phone="111", is_public=True, is_active=True)
        self.pharmacy = pharmacy
        user = User.objects.create_user(email="staff@test.local", password="Password123!", role=UserRole.PHARMACY_STAFF, pharmacy=pharmacy)
        medicine = Medicine.objects.create(
            brand_name="Panadol",
            generic_name="Paracetamol",
            strength="500mg",
            form="Tablet",
            price_regime=PriceRegime.FREE,
        )
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

    def test_public_search_finds_a_medicine_by_alias(self):
        response = self.client.get("/api/public/search/?q=acetaminophen")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]["availability_status"], "Low stock")
        self.assertIn("confirm", response.data[0]["disclaimer"].lower())

    def test_public_search_never_exposes_stock_depth_beyond_the_cap(self):
        """
        The contract, deliberately chosen: shoppers see an ORDERABLE CEILING
        (`available_up_to`), never the pharmacy's true stock depth.

        A shopper has to know how much they can actually buy, so a number is unavoidable -
        but it is clamped to PUBLIC_MAX_QUANTITY_PER_ITEM. The leak is therefore bounded by
        the cap, and internal fields (current_quantity, reserved_quantity, batch ids,
        purchase_cost) never appear at all.
        """
        with self.settings(PUBLIC_MAX_QUANTITY_PER_ITEM=2):
            response = self.client.get("/api/public/search/?q=acetaminophen")

        row = response.data[0]
        self.assertEqual(row["available_up_to"], 2, "stock of 3 must be reported as the cap of 2, not the true figure")
        self.assertEqual(row["quantity_cap"], 2)
        body = str(response.data).lower()
        for leaked in ("current_quantity", "reserved_quantity", "purchase_cost", "initial_quantity", "batch_number"):
            self.assertNotIn(leaked, body)

    def test_deep_stock_is_reported_only_up_to_the_cap(self):
        batch = self.pharmacy.inventory_batches.get()
        batch.current_quantity = 500
        batch.save(update_fields=["current_quantity"])

        with self.settings(PUBLIC_MAX_QUANTITY_PER_ITEM=10):
            response = self.client.get("/api/public/search/?q=acetaminophen")

        row = response.data[0]
        self.assertEqual(row["available_up_to"], 10)
        self.assertNotEqual(row["available_up_to"], 500)
        self.assertEqual(row["availability_status"], "Available")

    def test_results_are_ranked_and_distance_appears_when_coordinates_are_given(self):
        self.pharmacy.latitude = Decimal("33.8975")
        self.pharmacy.longitude = Decimal("35.4790")
        self.pharmacy.save(update_fields=["latitude", "longitude"])

        response = self.client.get("/api/public/search/?q=acetaminophen&lat=33.8991&lng=35.4772")

        row = response.data[0]
        self.assertIsNotNone(row["distance_km"])
        self.assertLess(row["distance_km"], 1.0)
        self.assertIn("rank_score", row)

    def test_a_search_with_no_results_is_recorded_as_unmet_demand(self):
        from apps.orders.models import UnmetDemandSignal

        response = self.client.get("/api/public/search/?q=nothing-like-this-exists&area=Hamra")

        self.assertEqual(response.data, [])
        signal = UnmetDemandSignal.objects.get()
        self.assertEqual(signal.query_text, "nothing-like-this-exists")
        self.assertEqual(signal.area, "Hamra")
