"""Re-uploading the exact same file should not silently double the stock."""

import io

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.models import UserRole
from apps.imports.services.workflow import DuplicateImportError, create_import_preview
from apps.medicines.models import Medicine
from apps.pharmacies.models import Pharmacy


class ImportDedupTests(TestCase):
    def setUp(self):
        self.pharmacy = Pharmacy.objects.create(name="Cedar Care", city="Beirut", area="Hamra", phone="+961-1-000-000")
        self.user = get_user_model().objects.create_user(email="owner@cedar.test", password="Password123!", role=UserRole.PHARMACY_OWNER, pharmacy=self.pharmacy)
        Medicine.objects.create(brand_name="Panadol", strength="500mg", form="Tablet", regulated_price="2.25")

    def _upload(self, content: str):
        upload = io.BytesIO(content.encode("utf-8"))
        upload.name = "stock.csv"
        return create_import_preview(uploaded_file=upload, user=self.user)

    def test_reuploading_the_identical_file_is_refused(self):
        content = "medicine name,quantity,selling price\nPanadol,10,2.25\n"
        self._upload(content)

        with self.assertRaises(DuplicateImportError):
            self._upload(content)

    def test_a_different_file_is_accepted(self):
        self._upload("medicine name,quantity,selling price\nPanadol,10,2.25\n")

        second = self._upload("medicine name,quantity,selling price\nPanadol,20,2.25\n")

        self.assertIsNotNone(second.id)
