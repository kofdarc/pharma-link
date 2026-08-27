"""
PrescriptionRecordViewSet.extract - the endpoint a pharmacist calls to get OCR candidate
lines for a scan. Mocks the OCR provider itself (covered separately in test_ocr.py) so this
suite is only about the view's own behaviour: caching, response shape, auditing, and that
nothing here creates a sale or otherwise acts on the candidates automatically.
"""

from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from apps.accounts.models import UserRole
from apps.audit.models import AuditLog
from apps.medicines.models import Medicine, PriceRegime, ProductCategory
from apps.pharmacies.models import Pharmacy
from apps.prescriptions.models import PrescriptionRecord
from apps.prescriptions.services.ocr.base import OcrResult, UnsupportedFileType


class PrescriptionExtractViewTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.pharmacy = Pharmacy.objects.create(name="Cedar Care", city="Beirut", area="Hamra", phone="111")
        self.staff = User.objects.create_user(email="staff@test.local", password="Password123!", role=UserRole.PHARMACY_STAFF, pharmacy=self.pharmacy)
        self.other_pharmacy = Pharmacy.objects.create(name="Other Pharmacy", city="Beirut", area="Verdun", phone="222")
        self.other_staff = get_user_model().objects.create_user(
            email="other@test.local", password="Password123!", role=UserRole.PHARMACY_STAFF, pharmacy=self.other_pharmacy
        )
        Medicine.objects.create(
            brand_name="Panadol",
            generic_name="Paracetamol",
            strength="500mg",
            form="Tablet",
            category=ProductCategory.MEDICINE,
            price_regime=PriceRegime.REGULATED,
            regulated_price=Decimal("2.25"),
        )
        self.record = PrescriptionRecord.objects.create(
            pharmacy=self.pharmacy,
            created_by=self.staff,
            file=SimpleUploadedFile("rx.png", b"fake-png-bytes", content_type="image/png"),
            file_original_name="rx.png",
            file_mime_type="image/png",
            file_size=14,
        )
        self.addCleanup(self.record.file.delete, save=False)
        self.client.force_authenticate(self.staff)

    def test_extract_returns_candidates_and_caches_ocr_text(self):
        with patch("apps.prescriptions.services.ocr.tesseract.TesseractOcrProvider.extract_text") as mock_extract:
            mock_extract.return_value = OcrResult(text="Panadol 500mg x30", provider="tesseract")
            response = self.client.post(f"/api/pharmacy/prescriptions/{self.record.id}/extract/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["provider"], "tesseract")
        self.assertEqual(len(response.data["candidates"]), 1)
        self.assertEqual(response.data["candidates"][0]["quantity_guess"], 30)
        mock_extract.assert_called_once()

        self.record.refresh_from_db()
        self.assertEqual(self.record.ocr_text, "Panadol 500mg x30")

    def test_second_call_reuses_cached_text_without_calling_the_provider_again(self):
        with patch("apps.prescriptions.services.ocr.tesseract.TesseractOcrProvider.extract_text") as mock_extract:
            mock_extract.return_value = OcrResult(text="Panadol 500mg x30", provider="tesseract")
            self.client.post(f"/api/pharmacy/prescriptions/{self.record.id}/extract/")
            self.client.post(f"/api/pharmacy/prescriptions/{self.record.id}/extract/")

        mock_extract.assert_called_once()

    def test_writes_an_audit_log_entry(self):
        with patch("apps.prescriptions.services.ocr.tesseract.TesseractOcrProvider.extract_text") as mock_extract:
            mock_extract.return_value = OcrResult(text="Panadol 500mg x30", provider="tesseract")
            self.client.post(f"/api/pharmacy/prescriptions/{self.record.id}/extract/")

        self.assertTrue(AuditLog.objects.filter(action="prescriptions.ocr_extracted", entity_id=self.record.id).exists())

    def test_unsupported_file_type_returns_400(self):
        with patch("apps.prescriptions.services.ocr.tesseract.TesseractOcrProvider.extract_text") as mock_extract:
            mock_extract.side_effect = UnsupportedFileType("nope")
            response = self.client.post(f"/api/pharmacy/prescriptions/{self.record.id}/extract/")

        self.assertEqual(response.status_code, 400)

    def test_record_with_no_file_returns_400(self):
        empty_record = PrescriptionRecord.objects.create(pharmacy=self.pharmacy, created_by=self.staff)

        response = self.client.post(f"/api/pharmacy/prescriptions/{empty_record.id}/extract/")

        self.assertEqual(response.status_code, 400)

    def test_a_pharmacy_cannot_extract_another_pharmacys_prescription(self):
        self.client.force_authenticate(self.other_staff)

        response = self.client.post(f"/api/pharmacy/prescriptions/{self.record.id}/extract/")

        self.assertEqual(response.status_code, 404)

    def test_nothing_is_created_or_dispensed_automatically(self):
        from apps.sales.models import Sale

        with patch("apps.prescriptions.services.ocr.tesseract.TesseractOcrProvider.extract_text") as mock_extract:
            mock_extract.return_value = OcrResult(text="Panadol 500mg x30", provider="tesseract")
            self.client.post(f"/api/pharmacy/prescriptions/{self.record.id}/extract/")

        self.assertEqual(Sale.objects.count(), 0)
