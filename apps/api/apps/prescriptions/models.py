from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.common.models import UUIDTimeStampedModel


ALLOWED_PRESCRIPTION_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
ALLOWED_PRESCRIPTION_MIME_TYPES = {"application/pdf", "image/jpeg", "image/png"}


def prescription_upload_path(instance, filename: str) -> str:
    safe_suffix = Path(filename).suffix.lower()
    return f"prescriptions/{instance.pharmacy_id}/{instance.id}{safe_suffix}"


def validate_prescription_file(file_obj):
    suffix = Path(file_obj.name).suffix.lower()
    if suffix not in ALLOWED_PRESCRIPTION_EXTENSIONS:
        raise ValidationError("Prescription file must be PDF, JPG, JPEG, or PNG.")
    max_bytes = settings.MAX_PRESCRIPTION_FILE_SIZE_MB * 1024 * 1024
    if file_obj.size > max_bytes:
        raise ValidationError(f"Prescription file must be {settings.MAX_PRESCRIPTION_FILE_SIZE_MB} MB or smaller.")


class PrescriptionRecord(UUIDTimeStampedModel):
    pharmacy = models.ForeignKey("pharmacies.Pharmacy", on_delete=models.PROTECT, related_name="prescription_records", db_index=True)
    sale = models.ForeignKey("sales.Sale", null=True, blank=True, on_delete=models.SET_NULL, related_name="prescription_records")
    patient_name = models.CharField(max_length=255, blank=True)
    patient_phone = models.CharField(max_length=60, blank=True)
    doctor_name = models.CharField(max_length=255, blank=True)
    prescription_date = models.DateField(null=True, blank=True)
    file = models.FileField(upload_to=prescription_upload_path, validators=[validate_prescription_file], blank=True)
    file_original_name = models.CharField(max_length=255, blank=True)
    file_mime_type = models.CharField(max_length=120, blank=True)
    file_size = models.PositiveIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="prescription_records")

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        if self.sale_id and self.sale.pharmacy_id != self.pharmacy_id:
            raise ValidationError("Prescription must belong to the same pharmacy as the linked sale.")

    @property
    def file_path(self) -> str:
        return self.file.name if self.file else ""

