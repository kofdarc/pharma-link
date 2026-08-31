"""
What must hold:
  - a prescription file is encrypted on disk - the raw bytes stored are not the upload
  - the authenticated download endpoint still returns the exact original bytes
"""

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from apps.accounts.models import UserRole
from apps.prescriptions.models import PrescriptionRecord

ORIGINAL_BYTES = b"%PDF-1.4 a real prescription would go here"


class PrescriptionFileEncryptionTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.shopper = User.objects.create_user(email="shopper@test.local", password="Password123!", role=UserRole.CUSTOMER)
        self.record = PrescriptionRecord.objects.create(
            customer=self.shopper,
            created_by=self.shopper,
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
        self.client.force_authenticate(self.shopper)
        response = self.client.get(f"/api/shop/prescription-uploads/{self.record.id}/file/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), ORIGINAL_BYTES)
