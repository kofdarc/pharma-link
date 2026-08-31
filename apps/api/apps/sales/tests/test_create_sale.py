from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.accounts.models import UserRole
from apps.inventory.models import StockMovement
from apps.inventory.services.stock import create_inventory_batch
from apps.medicines.models import MarketStatus, Medicine, PriceRegime
from apps.pharmacies.models import Pharmacy


class SaleCreationTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.pharmacy = Pharmacy.objects.create(name="Cedar Care", city="Beirut", area="Hamra", phone="111")
        self.staff = User.objects.create_user(email="staff@test.local", password="Password123!", role=UserRole.PHARMACY_STAFF, pharmacy=self.pharmacy)
        self.medicine = Medicine.objects.create(
            brand_name="Panadol", generic_name="Paracetamol", strength="500mg", form="Tablet", price_regime=PriceRegime.FREE
        )
        self.batch = create_inventory_batch(
            user=self.staff,
            pharmacy=self.pharmacy,
            data={"medicine": self.medicine, "initial_quantity": 5, "selling_price": Decimal("2.00")},
        )

    def test_sale_deducts_stock_and_creates_movement(self):
        self.client.force_authenticate(self.staff)
        response = self.client.post(
            "/api/pharmacy/sales/",
            {"items": [{"medicine": str(self.medicine.id), "quantity": 3, "unit_price": "2.00"}], "payment_method": "CASH"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.current_quantity, 2)
        self.assertTrue(StockMovement.objects.filter(inventory_batch=self.batch, movement_type=StockMovement.MovementType.SALE).exists())

    def test_sale_blocks_insufficient_stock(self):
        self.client.force_authenticate(self.staff)
        response = self.client.post(
            "/api/pharmacy/sales/",
            {"items": [{"medicine": str(self.medicine.id), "quantity": 99, "unit_price": "2.00"}]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_non_marketed_medicine_cannot_be_sold(self):
        self.medicine.market_status = MarketStatus.NON_MARKETED
        self.medicine.save(update_fields=["market_status"])
        self.client.force_authenticate(self.staff)

        response = self.client.post(
            "/api/pharmacy/sales/",
            {"items": [{"medicine": str(self.medicine.id), "quantity": 1, "unit_price": "2.00"}], "payment_method": "CASH"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_prescription_required_medicine_cannot_be_sold_without_one(self):
        self.medicine.requires_prescription = True
        self.medicine.save(update_fields=["requires_prescription"])
        self.client.force_authenticate(self.staff)

        response = self.client.post(
            "/api/pharmacy/sales/",
            {"items": [{"medicine": str(self.medicine.id), "quantity": 1, "unit_price": "2.00"}], "payment_method": "CASH"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_paper_record_id_cannot_authorize_a_counter_sale(self):
        self.medicine.requires_prescription = True
        self.medicine.save(update_fields=["requires_prescription"])
        self.client.force_authenticate(self.staff)

        response = self.client.post(
            "/api/pharmacy/sales/",
            {
                "items": [{"medicine": str(self.medicine.id), "quantity": 1, "unit_price": "2.00"}],
                "payment_method": "CASH",
                "prescription_record_id": "00000000-0000-0000-0000-000000000001",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)

