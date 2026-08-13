"""
What must hold:
  - a prescription file is encrypted on disk - the raw bytes stored are not the upload
  - the authenticated download endpoint still returns the exact original bytes
"""

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from apps.accounts.models import UserRole
from apps.pharmacies.models import Pharmacy
from apps.prescriptions.models import PrescriptionRecord

ORIGINAL_BYTES = b"%PDF-1.4 a real prescription would go here"


class PrescriptionFileEncryptionTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.pharmacy = Pharmacy.objects.create(name="Alpha Pharmacy", city="Beirut", area="Hamra", phone="111")
        self.staff = User.objects.create_user(email="staff@test.local", password="Password123!", role=UserRole.PHARMACY_STAFF, pharmacy=self.pharmacy)
        self.record = PrescriptionRecord.objects.create(
            pharmacy=self.pharmacy,
            created_by=self.staff,
            file=SimpleUploadedFile("rx.pdf", ORIGINAL_BYTES, content_type="application/pdf"),
            file_original_name="rx.pdf",
            file_mime_type="application/pdf",
            file_size=len(ORIGINAL_BYTES),
        )
        self.addCleanup(self.record.file.delete, save=False)

    def test_file_is_encrypted_on_disk(self):
        with open(self.record.file.path, "rb") as raw:
            on_disk = raw.read()
        self.assertNotEqual(on_disk, ORIGINAL_BYTES)
        self.assertNotIn(ORIGINAL_BYTES, on_disk)

    def test_download_returns_the_original_bytes(self):
        self.client.force_authenticate(self.staff)
        response = self.client.get(f"/api/pharmacy/prescriptions/{self.record.id}/download/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), ORIGINAL_BYTES)
