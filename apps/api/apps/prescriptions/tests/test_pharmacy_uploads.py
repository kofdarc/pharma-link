"""
PharmacyPrescriptionUploadViewSet - the pharmacy queue for patient paper uploads: claim,
correct the OCR read inline, accept or reject. OCR is mocked (covered in test_ocr.py /
test_structured.py); this suite is about the view's behaviour.
"""

import io
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.accounts.models import UserRole
from apps.pharmacies.models import Pharmacy
from apps.prescriptions.models import PrescriptionRecord
from apps.prescriptions.services.ocr.base import OcrResult

SHOP_URL = "/api/shop/prescription-uploads/"
PHARM_URL = "/api/pharmacy/prescription-uploads/"

RX_TEXT = "Dr. Rima Khalil\nPatient: John Smith\nDate: 14/03/2026\nPanadol 500mg x30 - 1 tab bid for 7 days\n"


def _png_bytes(w=800, h=1000):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (w, h), (200, 200, 200)).save(buf, format="PNG")
    return buf.getvalue()


def _scan(name="rx.png"):
    return SimpleUploadedFile(name, _png_bytes(), content_type="image/png")


@override_settings(PRESCRIPTION_OCR_PROVIDER="tesseract", PRESCRIPTION_NLP_PROVIDER="regex")
class PharmacyPrescriptionUploadTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.shopper = User.objects.create_user(email="shopper@test.local", password="Password123!", role=UserRole.CUSTOMER)
        self.pharmacy_a = Pharmacy.objects.create(name="Alpha Pharmacy", city="Beirut", area="Hamra", phone="111")
        self.pharmacy_b = Pharmacy.objects.create(name="Beta Pharmacy", city="Beirut", area="Verdun", phone="222")
        self.staff_a = User.objects.create_user(
            email="a@test.local", password="Password123!", role=UserRole.PHARMACY_STAFF, pharmacy=self.pharmacy_a
        )
        self.staff_b = User.objects.create_user(
            email="b@test.local", password="Password123!", role=UserRole.PHARMACY_STAFF, pharmacy=self.pharmacy_b
        )

    def _upload(self):
        self.client.force_authenticate(self.shopper)
        with patch(
            "apps.prescriptions.services.ocr.tesseract.TesseractOcrProvider.extract_text",
            return_value=OcrResult(text=RX_TEXT, provider="tesseract"),
        ):
            response = self.client.post(SHOP_URL, {"file": _scan()}, format="multipart")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def test_upload_populates_structured_fields_and_scalar_columns(self):
        data = self._upload()
        self.assertEqual(data["ocr_fields"]["doctor_name"], "Dr. Rima Khalil")
        self.assertEqual(len(data["ocr_fields"]["medications"]), 1)

        record = PrescriptionRecord.objects.get(id=data["id"])
        self.assertEqual(record.doctor_name, "Dr. Rima Khalil")
        self.assertEqual(record.patient_name, "John Smith")
        self.assertEqual(record.prescription_date.isoformat(), "2026-03-14")

    def test_ocr_fields_are_read_only_for_the_patient(self):
        self.client.force_authenticate(self.shopper)
        with patch(
            "apps.prescriptions.services.ocr.tesseract.TesseractOcrProvider.extract_text",
            return_value=OcrResult(text=RX_TEXT, provider="tesseract"),
        ):
            response = self.client.post(
                SHOP_URL, {"file": _scan(), "ocr_fields": '{"doctor_name": "Dr. Fake"}'}, format="multipart"
            )
        self.assertEqual(response.data["ocr_fields"]["doctor_name"], "Dr. Rima Khalil")

    def test_patient_can_flag_the_ocr_read(self):
        data = self._upload()
        self.client.force_authenticate(self.shopper)
        response = self.client.post(f"{SHOP_URL}{data['id']}/flag/", {"note": "Wrong doctor name"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["ocr_review_requested"])

        record = PrescriptionRecord.objects.get(id=data["id"])
        self.assertEqual(record.ocr_review_note, "Wrong doctor name")
        self.assertTrue(any(f["code"] == "patient_flagged_ocr" for f in record.quality_findings))

    def test_flag_on_a_reviewed_upload_conflicts(self):
        data = self._upload()
        PrescriptionRecord.objects.filter(id=data["id"]).update(status=PrescriptionRecord.UploadStatus.ACCEPTED)
        self.client.force_authenticate(self.shopper)
        self.assertEqual(self.client.post(f"{SHOP_URL}{data['id']}/flag/", {}, format="json").status_code, 409)

    def test_unclaimed_upload_is_visible_to_any_pharmacy_then_scoped_after_a_claim(self):
        data = self._upload()

        self.client.force_authenticate(self.staff_a)
        self.assertEqual(len(_results(self.client.get(PHARM_URL))), 1)
        self.client.force_authenticate(self.staff_b)
        self.assertEqual(len(_results(self.client.get(PHARM_URL))), 1)

        # staff_a edits -> claims it for pharmacy A
        self.client.force_authenticate(self.staff_a)
        patched = self.client.patch(
            f"{PHARM_URL}{data['id']}/",
            {"ocr_fields": {"doctor_name": "Dr. R. Khalil", "medications": []}, "patient_name": "Jon Smith"},
            format="json",
        )
        self.assertEqual(patched.status_code, 200, patched.data)
        self.assertEqual(patched.data["ocr_fields"]["doctor_name"], "Dr. R. Khalil")

        record = PrescriptionRecord.objects.get(id=data["id"])
        self.assertEqual(record.pharmacy_id, self.pharmacy_a.id)
        self.assertEqual(record.patient_name, "Jon Smith")

        self.client.force_authenticate(self.staff_b)
        self.assertEqual(len(_results(self.client.get(PHARM_URL))), 0)
        self.assertEqual(self.client.get(f"{PHARM_URL}{data['id']}/").status_code, 404)

    def test_accept_and_reject(self):
        first = self._upload()
        second = self._upload()

        self.client.force_authenticate(self.staff_a)
        accepted = self.client.post(f"{PHARM_URL}{first['id']}/accept/")
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.data["status"], "ACCEPTED")

        self.assertEqual(self.client.post(f"{PHARM_URL}{second['id']}/reject/", {}, format="json").status_code, 400)
        rejected = self.client.post(f"{PHARM_URL}{second['id']}/reject/", {"reason": "Illegible"}, format="json")
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(rejected.data["status"], "REJECTED")
        self.assertEqual(PrescriptionRecord.objects.get(id=second["id"]).rejection_reason, "Illegible")

    def test_shopper_cannot_use_the_pharmacy_endpoint(self):
        data = self._upload()
        self.client.force_authenticate(self.shopper)
        self.assertEqual(self.client.get(PHARM_URL).status_code, 403)
        self.assertEqual(self.client.post(f"{PHARM_URL}{data['id']}/accept/").status_code, 403)

    def test_pharmacy_can_view_the_scan(self):
        data = self._upload()
        self.client.force_authenticate(self.staff_a)
        response = self.client.get(f"{PHARM_URL}{data['id']}/file/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content)[:8], b"\x89PNG\r\n\x1a\n")


def _results(response):
    body = response.data
    return body["results"] if isinstance(body, dict) and "results" in body else body
