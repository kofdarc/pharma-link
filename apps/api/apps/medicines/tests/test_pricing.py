"""
Pricing regime rules.

Lebanon splits pharmacy products in two: medicine prices are set by the Ministry of Public
Health and are not the pharmacy's to choose, while supplements and parapharmacy are freely
priced. Every path that sets a price has to respect that split - stock entry, imports,
counter sales and the consumer quote.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import UserRole
from apps.inventory.serializers import InventoryBatchSerializer
from apps.inventory.services.stock import create_inventory_batch
from apps.medicines.models import Medicine, PriceRegime, ProductCategory
from apps.pharmacies.models import Pharmacy
from apps.sales.services.create_sale import create_sale


class PricingTestCase(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        self.pharmacy = Pharmacy.objects.create(name="Cedar Care", area="Hamra", city="Beirut", phone="+961-1-000-000")
        self.user = get_user_model().objects.create_user(
            email="owner@cedar.test", password="Password123!", role=UserRole.PHARMACY_OWNER, pharmacy=self.pharmacy
        )
        self.regulated = Medicine.objects.create(
            brand_name="Panadol",
            strength="500mg",
            form="Tablet",
            category=ProductCategory.MEDICINE,
            price_regime=PriceRegime.REGULATED,
            regulated_price=Decimal("2.25"),
        )
        self.free = Medicine.objects.create(
            brand_name="Omega 3",
            strength="1000mg",
            form="Softgel",
            category=ProductCategory.SUPPLEMENT,
            price_regime=PriceRegime.FREE,
            regulated_price=None,
        )

    def batch_data(self, medicine, price):
        return {
            "medicine": medicine,
            "batch_number": "B-1",
            "initial_quantity": 10,
            "expiry_date": timezone.localdate() + timezone.timedelta(days=200),
            "purchase_cost": Decimal("1.00"),
            "selling_price": price,
            "low_stock_threshold": 3,
        }


class RegulatedPriceTests(PricingTestCase):
    def test_regulated_medicine_must_be_stocked_at_the_moph_price(self):
        with self.assertRaises(ValidationError) as context:
            create_inventory_batch(user=self.user, pharmacy=self.pharmacy, data=self.batch_data(self.regulated, Decimal("2.95")))

        self.assertIn("Ministry of Public Health", str(context.exception))

    def test_undercutting_the_moph_price_is_also_refused(self):
        # The published price is the price, not a ceiling.
        with self.assertRaises(ValidationError):
            create_inventory_batch(user=self.user, pharmacy=self.pharmacy, data=self.batch_data(self.regulated, Decimal("1.50")))

    def test_the_moph_price_itself_is_accepted(self):
        batch = create_inventory_batch(user=self.user, pharmacy=self.pharmacy, data=self.batch_data(self.regulated, Decimal("2.25")))

        self.assertEqual(batch.selling_price, Decimal("2.25"))

    def test_a_pharmacy_sets_its_own_price_on_free_priced_products(self):
        cheap = create_inventory_batch(user=self.user, pharmacy=self.pharmacy, data=self.batch_data(self.free, Decimal("18.00")))

        self.assertEqual(cheap.selling_price, Decimal("18.00"))

    def test_serializer_rejects_an_off_price_regulated_batch(self):
        serializer = InventoryBatchSerializer(data={"medicine": str(self.regulated.id), "initial_quantity": 5, "selling_price": "3.50"})

        self.assertFalse(serializer.is_valid())
        self.assertIn("selling_price", serializer.errors)

    def test_selling_a_regulated_item_off_price_is_refused(self):
        create_inventory_batch(user=self.user, pharmacy=self.pharmacy, data=self.batch_data(self.regulated, Decimal("2.25")))

        with self.assertRaises(ValidationError):
            create_sale(
                user=self.user,
                pharmacy=self.pharmacy,
                items=[{"medicine": self.regulated.id, "quantity": 1, "unit_price": Decimal("4.00")}],
            )

    def test_selling_at_the_regulated_price_succeeds(self):
        create_inventory_batch(user=self.user, pharmacy=self.pharmacy, data=self.batch_data(self.regulated, Decimal("2.25")))

        sale = create_sale(user=self.user, pharmacy=self.pharmacy, items=[{"medicine": self.regulated.id, "quantity": 2}])

        self.assertEqual(sale.total, Decimal("4.50"))

    def test_a_regulated_product_cannot_exist_without_a_published_price(self):
        medicine = Medicine(brand_name="Mystery", price_regime=PriceRegime.REGULATED, regulated_price=None)

        with self.assertRaises(ValidationError):
            medicine.clean()

    def test_free_priced_products_have_no_regulated_price_to_enforce(self):
        self.assertFalse(self.free.is_price_regulated)
        self.free.validate_selling_price(Decimal("999.00"))  # must not raise


class RegulatedPriceAuditTests(PricingTestCase):
    def test_changing_the_regulated_price_writes_an_audit_log(self):
        from django.contrib.auth import get_user_model
        from rest_framework.test import APIClient

        from apps.accounts.models import UserRole
        from apps.audit.models import AuditLog

        admin = get_user_model().objects.create_user(email="admin@platform.test", password="Password123!", role=UserRole.PLATFORM_ADMIN)
        client = APIClient()
        client.force_authenticate(admin)

        response = client.patch(f"/api/admin/medicines/{self.regulated.id}/", {"regulated_price": "2.75"}, format="json")

        self.assertEqual(response.status_code, 200, response.data)
        log = AuditLog.objects.filter(action="medicines.price_updated", entity_id=str(self.regulated.id)).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.before_data["regulated_price"], "2.25")
        self.assertEqual(log.after_data["regulated_price"], "2.75")

    def test_unrelated_field_changes_do_not_write_a_price_audit_log(self):
        from django.contrib.auth import get_user_model
        from rest_framework.test import APIClient

        from apps.accounts.models import UserRole
        from apps.audit.models import AuditLog

        admin = get_user_model().objects.create_user(email="admin2@platform.test", password="Password123!", role=UserRole.PLATFORM_ADMIN)
        client = APIClient()
        client.force_authenticate(admin)

        response = client.patch(f"/api/admin/medicines/{self.regulated.id}/", {"classification": "Analgesic"}, format="json")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(AuditLog.objects.filter(action="medicines.price_updated", entity_id=str(self.regulated.id)).exists())


class ImportPriceSnappingTests(PricingTestCase):
    def test_import_replaces_an_off_price_with_the_moph_price_instead_of_failing_the_row(self):
        """
        Onboarding reality: a pharmacy's export will contain stale prices. Failing the whole
        import would block them, so regulated rows are snapped to the published price and
        the change is surfaced on the row.
        """
        import io

        from apps.imports.models import InventoryImportRow
        from apps.imports.services.workflow import create_import_preview

        csv_content = "medicine name,quantity,selling price\nPanadol,10,9.99\n"
        upload = io.BytesIO(csv_content.encode("utf-8"))
        upload.name = "stock.csv"

        inventory_import = create_import_preview(uploaded_file=upload, user=self.user)
        row = inventory_import.rows.get()

        self.assertEqual(row.status, InventoryImportRow.Status.VALID_MATCHED)
        self.assertEqual(row.selling_price, Decimal("2.25"))
        self.assertIn("MoPH regulated price", row.price_note)
