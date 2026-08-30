"""
NSSF (National Social Security Fund) reimbursement coverage on the medicine catalog.

The NSSF publishes its own formulary of reimbursable drugs with a reference price and a
reimbursement rate. The platform has no NSSF feed, so coverage is edited by a platform
admin (or a one-off import). These tests pin the model rules, the derived patient-share
figure, the admin write path with its audit log, and the public exposure of the fields.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import UserRole
from apps.audit.models import AuditLog
from apps.inventory.services.stock import create_inventory_batch
from apps.medicines.models import Medicine, PriceRegime, ProductCategory
from apps.pharmacies.models import Pharmacy


class NssfModelTests(TestCase):
    def test_patient_share_is_the_complement_of_the_reimbursement_rate(self):
        medicine = Medicine.objects.create(
            brand_name="Glucophage",
            strength="850mg",
            form="Tablet",
            price_regime=PriceRegime.FREE,
            nssf_covered=True,
            nssf_reimbursement_rate=Decimal("80.00"),
        )
        self.assertEqual(medicine.nssf_patient_share_percentage, Decimal("20.00"))

    def test_patient_share_is_unknown_when_covered_but_no_rate_on_file(self):
        medicine = Medicine.objects.create(brand_name="Aspirin", strength="100mg", form="Tablet", price_regime=PriceRegime.FREE, nssf_covered=True)
        self.assertIsNone(medicine.nssf_patient_share_percentage)

    def test_patient_share_is_none_when_not_covered(self):
        medicine = Medicine.objects.create(brand_name="Nurofen", strength="400mg", form="Tablet", price_regime=PriceRegime.FREE, nssf_covered=False)
        self.assertIsNone(medicine.nssf_patient_share_percentage)

    def test_reference_price_without_coverage_is_rejected(self):
        medicine = Medicine(brand_name="Ghost", price_regime=PriceRegime.FREE, nssf_covered=False, nssf_reference_price=Decimal("3.00"))
        with self.assertRaises(ValidationError):
            medicine.clean()


class NssfAdminApiTests(TestCase):
    def setUp(self):
        self.medicine = Medicine.objects.create(brand_name="Concor", strength="5mg", form="Tablet", price_regime=PriceRegime.FREE)
        admin = get_user_model().objects.create_user(
            email="admin@platform.test", password="Password123!", role=UserRole.PLATFORM_ADMIN
        )
        self.client = APIClient()
        self.client.force_authenticate(admin)

    def test_marking_a_medicine_nssf_covered_stamps_the_timestamp_and_audits(self):
        response = self.client.patch(
            f"/api/admin/medicines/{self.medicine.id}/",
            {"nssf_covered": True, "nssf_reference_price": "4.50", "nssf_reimbursement_rate": "80", "nssf_source_reference": "NSSF list 17-04-2025 (80%)"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["nssf_covered"])
        self.assertEqual(response.data["nssf_patient_share_percentage"], "20.00")
        self.assertIsNotNone(response.data["nssf_updated_at"])

        log = AuditLog.objects.filter(action="medicines.nssf_coverage_updated", entity_id=str(self.medicine.id)).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.before_data["nssf_covered"], False)
        self.assertEqual(log.after_data["nssf_covered"], True)
        self.assertEqual(log.after_data["nssf_reimbursement_rate"], "80.00")

    def test_unchecking_coverage_clears_reference_price_and_rate(self):
        self.medicine.nssf_covered = True
        self.medicine.nssf_reference_price = Decimal("4.50")
        self.medicine.nssf_reimbursement_rate = Decimal("80.00")
        self.medicine.save()

        response = self.client.patch(f"/api/admin/medicines/{self.medicine.id}/", {"nssf_covered": False}, format="json")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data["nssf_covered"])
        self.assertIsNone(response.data["nssf_reference_price"])
        self.assertIsNone(response.data["nssf_reimbursement_rate"])

    def test_unrelated_edit_does_not_write_an_nssf_audit_log(self):
        response = self.client.patch(f"/api/admin/medicines/{self.medicine.id}/", {"classification": "Beta blocker"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(
            AuditLog.objects.filter(action="medicines.nssf_coverage_updated", entity_id=str(self.medicine.id)).exists()
        )

    def test_covered_filter_narrows_the_list(self):
        covered = Medicine.objects.create(brand_name="Covered One", strength="1mg", form="Tablet", price_regime=PriceRegime.FREE, nssf_covered=True)
        Medicine.objects.create(brand_name="Uncovered One", strength="1mg", form="Tablet", price_regime=PriceRegime.FREE, nssf_covered=False)

        response = self.client.get("/api/admin/medicines/?nssf_covered=true")

        self.assertEqual(response.status_code, 200)
        returned = {row["id"] for row in response.data["results"]}
        self.assertIn(str(covered.id), returned)
        self.assertNotIn(str(self.medicine.id), returned)


class NssfPublicSearchTests(TestCase):
    def test_public_search_row_carries_nssf_fields(self):
        pharmacy = Pharmacy.objects.create(
            name="Cedar Care", area="Hamra", city="Beirut", phone="+961-1-000-000", is_public=True, is_active=True
        )
        owner = get_user_model().objects.create_user(
            email="owner@cedar.test", password="Password123!", role=UserRole.PHARMACY_OWNER, pharmacy=pharmacy
        )
        medicine = Medicine.objects.create(
            brand_name="Lipitor",
            strength="20mg",
            form="Tablet",
            category=ProductCategory.MEDICINE,
            price_regime=PriceRegime.REGULATED,
            regulated_price=Decimal("12.00"),
            nssf_covered=True,
            nssf_reference_price=Decimal("9.00"),
            nssf_reimbursement_rate=Decimal("80.00"),
        )
        create_inventory_batch(
            user=owner,
            pharmacy=pharmacy,
            data={
                "medicine": medicine,
                "batch_number": "B-1",
                "initial_quantity": 20,
                "expiry_date": timezone.localdate() + timezone.timedelta(days=200),
                "purchase_cost": Decimal("6.00"),
                "selling_price": Decimal("12.00"),
                "low_stock_threshold": 3,
                "public_availability_enabled": True,
            },
        )

        response = self.client.get("/api/public/search/?q=Lipitor")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data)
        row = response.data[0]["medicine"]
        self.assertTrue(row["nssf_covered"])
        self.assertEqual(row["nssf_reference_price"], "9.00")
        self.assertEqual(row["nssf_reimbursement_rate"], "80.00")
