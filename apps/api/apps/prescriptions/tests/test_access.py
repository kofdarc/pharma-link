from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

from apps.accounts.models import UserRole
from apps.pharmacies.models import Pharmacy
from apps.prescriptions.models import PrescriptionRecord


class PrescriptionAccessTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.pharmacy_a = Pharmacy.objects.create(name="Alpha Pharmacy", city="Beirut", area="Hamra", phone="111")
        self.pharmacy_b = Pharmacy.objects.create(name="Beta Pharmacy", city="Beirut", area="Achrafieh", phone="222")
        self.staff_a = User.objects.create_user(email="staff-a@test.local", password="Password123!", role=UserRole.PHARMACY_STAFF, pharmacy=self.pharmacy_a)
        self.staff_b = User.objects.create_user(email="staff-b@test.local", password="Password123!", role=UserRole.PHARMACY_STAFF, pharmacy=self.pharmacy_b)
        self.record = PrescriptionRecord.objects.create(
            pharmacy=self.pharmacy_a,
            created_by=self.staff_a,
            file=SimpleUploadedFile("rx.pdf", b"%PDF-1.4 test", content_type="application/pdf"),
            file_original_name="rx.pdf",
            file_mime_type="application/pdf",
            file_size=13,
        )

    def test_public_user_cannot_download_prescription(self):
        response = self.client.get(f"/api/pharmacy/prescriptions/{self.record.id}/download/")
        self.assertEqual(response.status_code, 401)

    def test_other_pharmacy_user_cannot_download_prescription(self):
        self.client.force_authenticate(self.staff_b)
        response = self.client.get(f"/api/pharmacy/prescriptions/{self.record.id}/download/")
        self.assertEqual(response.status_code, 404)

