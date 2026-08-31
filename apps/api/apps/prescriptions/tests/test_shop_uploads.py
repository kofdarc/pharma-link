import io
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.accounts.models import UserRole
from apps.pharmacies.models import Pharmacy
from apps.prescriptions.models import PrescriptionRecord

LIST_URL = "/api/shop/prescription-uploads/"


def _png_bytes(width, height, colour=(140, 140, 140)):
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (width, height), colour).save(buffer, format="PNG")
    return buffer.getvalue()


def _readable_scan(name="rx.png"):
    return SimpleUploadedFile(name, _png_bytes(800, 1000), content_type="image/png")


# Keep the upload path off any real LLM endpoint a local .env may configure - these tests
# exercise the view/flow, not OCR or extraction.
@override_settings(PRESCRIPTION_OCR_PROVIDER="tesseract", PRESCRIPTION_NLP_PROVIDER="regex")
class ShopPrescriptionUploadTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.shopper = User.objects.create_user(email="shopper@test.local", password="Password123!", role=UserRole.CUSTOMER)
        self.other_shopper = User.objects.create_user(email="other@test.local", password="Password123!", role=UserRole.CUSTOMER)
        self.pharmacy = Pharmacy.objects.create(name="Alpha Pharmacy", city="Beirut", area="Hamra", phone="111")
        self.staff = User.objects.create_user(
            email="staff@test.local", password="Password123!", role=UserRole.PHARMACY_STAFF, pharmacy=self.pharmacy
        )

    def test_preview_returns_structured_fields_without_storing_anything(self):
        from apps.prescriptions.services.ocr.base import OcrResult

        self.client.force_authenticate(self.shopper)
        text = "Dr. Rima Khalil\nDate: 14/03/2026\nPanadol 500mg x30 - 1 tab bid\n"
        with patch(
            "apps.prescriptions.services.ocr.tesseract.TesseractOcrProvider.extract_text",
            return_value=OcrResult(text=text, provider="tesseract"),
        ):
            response = self.client.post(f"{LIST_URL}preview/", {"file": _readable_scan()}, format="multipart")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["ocr_fields"]["doctor_name"], "Dr. Rima Khalil")
        self.assertEqual(len(response.data["ocr_fields"]["medications"]), 1)
        self.assertFalse(PrescriptionRecord.objects.filter(customer=self.shopper).exists())

    def test_preview_degrades_to_null_when_ocr_is_unavailable(self):
        from apps.prescriptions.services.ocr.base import OcrProviderError

        self.client.force_authenticate(self.shopper)
        with patch(
            "apps.prescriptions.services.ocr.tesseract.TesseractOcrProvider.extract_text",
            side_effect=OcrProviderError("down"),
        ):
            response = self.client.post(f"{LIST_URL}preview/", {"file": _readable_scan()}, format="multipart")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["ocr_fields"])

    def test_preview_rejects_a_wrong_file_type(self):
        self.client.force_authenticate(self.shopper)
        bad = SimpleUploadedFile("notes.txt", b"text", content_type="text/plain")
        self.assertEqual(self.client.post(f"{LIST_URL}preview/", {"file": bad}, format="multipart").status_code, 400)

    def test_preview_requires_a_shopper(self):
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.post(f"{LIST_URL}preview/", {"file": _readable_scan()}, format="multipart").status_code, 403)

    @patch("apps.prescriptions.views.run_structured_extraction", return_value=False)
    def test_shopper_uploads_a_private_paper_prescription(self, _extract):
        self.client.force_authenticate(self.shopper)
        response = self.client.post(LIST_URL, {"file": _readable_scan(), "doctor_name": "Dr. Haddad"}, format="multipart")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["status"], "PENDING_REVIEW")
        self.assertEqual(response.data["file_name"], "rx.png")

        record = PrescriptionRecord.objects.get(id=response.data["id"])
        self.assertEqual(record.customer_id, self.shopper.id)
        self.assertEqual(record.created_by_id, self.shopper.id)
        self.assertIsNone(record.pharmacy_id)

    @patch("apps.prescriptions.views.run_structured_extraction", return_value=False)
    def test_upload_list_is_scoped_to_the_uploader(self, _extract):
        self.client.force_authenticate(self.shopper)
        created = self.client.post(LIST_URL, {"file": _readable_scan()}, format="multipart")
        record_id = created.data["id"]

        self.client.force_authenticate(self.other_shopper)
        listing = self.client.get(LIST_URL)
        self.assertEqual(listing.status_code, 200)
        results = listing.data["results"] if isinstance(listing.data, dict) else listing.data
        self.assertEqual(results, [])
        self.assertEqual(self.client.get(f"{LIST_URL}{record_id}/").status_code, 404)
        self.assertEqual(self.client.get(f"{LIST_URL}{record_id}/file/").status_code, 404)

    def test_unreadable_scan_is_refused_and_nothing_is_stored(self):
        self.client.force_authenticate(self.shopper)
        tiny = SimpleUploadedFile("rx.png", _png_bytes(120, 90), content_type="image/png")
        response = self.client.post(LIST_URL, {"file": tiny}, format="multipart")
        self.assertEqual(response.status_code, 400)
        self.assertIn("file", response.data)
        self.assertFalse(PrescriptionRecord.objects.filter(customer=self.shopper).exists())

    def test_wrong_file_type_is_refused(self):
        self.client.force_authenticate(self.shopper)
        bad = SimpleUploadedFile("notes.txt", b"just some text", content_type="text/plain")
        response = self.client.post(LIST_URL, {"file": bad}, format="multipart")
        self.assertEqual(response.status_code, 400)

    def test_pharmacy_user_cannot_use_the_shop_endpoint(self):
        self.client.force_authenticate(self.staff)
        self.assertEqual(self.client.get(LIST_URL).status_code, 403)
        self.assertEqual(self.client.post(LIST_URL, {"file": _readable_scan()}, format="multipart").status_code, 403)
        self.assertEqual(self.client.get("/api/pharmacy/prescription-uploads/").status_code, 404)
        self.assertEqual(self.client.get("/api/pharmacy/prescriptions/").status_code, 404)

    def test_anonymous_caller_is_rejected(self):
        self.assertEqual(self.client.get(LIST_URL).status_code, 401)

    @patch("apps.prescriptions.views.run_structured_extraction", return_value=False)
    def test_owner_can_delete_a_pending_upload_but_not_an_accepted_one(self, _extract):
        self.client.force_authenticate(self.shopper)
        record_id = self.client.post(LIST_URL, {"file": _readable_scan()}, format="multipart").data["id"]

        PrescriptionRecord.objects.filter(id=record_id).update(status=PrescriptionRecord.UploadStatus.ACCEPTED)
        self.assertEqual(self.client.delete(f"{LIST_URL}{record_id}/").status_code, 409)

        PrescriptionRecord.objects.filter(id=record_id).update(status=PrescriptionRecord.UploadStatus.PENDING_REVIEW)
        self.assertEqual(self.client.delete(f"{LIST_URL}{record_id}/").status_code, 204)
        self.assertFalse(PrescriptionRecord.objects.filter(id=record_id).exists())

    @patch("apps.prescriptions.views.run_structured_extraction", return_value=False)
    def test_owner_can_download_their_own_file(self, _extract):
        self.client.force_authenticate(self.shopper)
        record_id = self.client.post(LIST_URL, {"file": _readable_scan()}, format="multipart").data["id"]
        response = self.client.get(f"{LIST_URL}{record_id}/file/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content)[:8], b"\x89PNG\r\n\x1a\n")

    def test_pharmacy_only_actions_are_not_exposed_on_the_shop_endpoint(self):
        # OCR is populated at upload time. No pharmacist review or legacy candidate
        # extraction action is exposed on the patient endpoint.
        from apps.prescriptions.views import ShopPrescriptionUploadViewSet

        action_names = {a.__name__ for a in ShopPrescriptionUploadViewSet.get_extra_actions()}
        self.assertNotIn("extract", action_names)
        self.assertEqual({"file", "preview"}, action_names)
