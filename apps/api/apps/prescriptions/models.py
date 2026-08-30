from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.common.models import UUIDTimeStampedModel
from apps.prescriptions.storage import EncryptedPrescriptionStorage

ALLOWED_PRESCRIPTION_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
ALLOWED_PRESCRIPTION_MIME_TYPES = {"application/pdf", "image/jpeg", "image/png"}

# Below this structured-OCR confidence (apps.prescriptions.services.structured.extraction_confidence)
# a patient upload is treated as "couldn't read it": the parsed medication list is withheld from
# the patient behind a "a pharmacist will check your photo" notice, and the scalar columns
# (doctor_name / patient_name / ...) are not auto-filled from the read.
OCR_LOW_CONFIDENCE_THRESHOLD = 0.45


def prescription_upload_path(instance, filename: str) -> str:
    safe_suffix = Path(filename).suffix.lower()
    # A pharmacy-created record keys by pharmacy; a patient upload has no pharmacy
    # yet, so it keys by the uploading customer instead.
    owner = instance.pharmacy_id or f"patient/{instance.customer_id}"
    return f"prescriptions/{owner}/{instance.id}{safe_suffix}"


def validate_prescription_file(file_obj):
    suffix = Path(file_obj.name).suffix.lower()
    if suffix not in ALLOWED_PRESCRIPTION_EXTENSIONS:
        raise ValidationError("Prescription file must be PDF, JPG, JPEG, or PNG.")
    max_bytes = settings.MAX_PRESCRIPTION_FILE_SIZE_MB * 1024 * 1024
    if file_obj.size > max_bytes:
        raise ValidationError(f"Prescription file must be {settings.MAX_PRESCRIPTION_FILE_SIZE_MB} MB or smaller.")


class PrescriptionRecord(UUIDTimeStampedModel):
    class UploadStatus(models.TextChoices):
        PENDING_REVIEW = "PENDING_REVIEW", "Pending review"
        ACCEPTED = "ACCEPTED", "Accepted"
        REJECTED = "REJECTED", "Rejected"

    # Nullable because a patient can upload a scan of their paper prescription
    # before any pharmacy is involved; a pharmacy claims it later. Pharmacy-created
    # records always set this.
    pharmacy = models.ForeignKey(
        "pharmacies.Pharmacy", null=True, blank=True, on_delete=models.PROTECT, related_name="prescription_records", db_index=True
    )
    # Set only on a patient-uploaded scan. `created_by` is the uploader in that case too,
    # but `customer` is the field views scope on and the "this is a patient upload" signal.
    customer = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.CASCADE, related_name="prescription_uploads", db_index=True
    )
    status = models.CharField(
        max_length=20,
        choices=UploadStatus.choices,
        default=UploadStatus.ACCEPTED,
        help_text="Pharmacy-created records are ACCEPTED by definition. A patient upload starts "
        "PENDING_REVIEW until a pharmacy accepts or rejects it.",
    )
    rejection_reason = models.CharField(max_length=500, blank=True)
    quality_findings = models.JSONField(
        default=list, blank=True, help_text="Server-side legibility check results at upload time ({code, message, severity})."
    )
    sale = models.ForeignKey("sales.Sale", null=True, blank=True, on_delete=models.SET_NULL, related_name="prescription_records")
    patient_name = models.CharField(max_length=255, blank=True)
    patient_phone = models.CharField(max_length=60, blank=True)
    doctor_name = models.CharField(max_length=255, blank=True)
    prescription_date = models.DateField(null=True, blank=True)
    valid_until = models.DateField(
        null=True,
        blank=True,
        help_text="After this date the scan can no longer back a new sale. Defaults to "
        "prescription_date + PRESCRIPTION_VALIDITY_DAYS if left blank.",
    )
    file = models.FileField(
        upload_to=prescription_upload_path, storage=EncryptedPrescriptionStorage(), validators=[validate_prescription_file], blank=True
    )
    file_original_name = models.CharField(max_length=255, blank=True)
    file_mime_type = models.CharField(max_length=120, blank=True)
    file_size = models.PositiveIntegerField(null=True, blank=True)
    ocr_text = models.TextField(
        blank=True, help_text="Cached raw OCR transcription of `file`, populated on first request to extract candidate drug lines."
    )
    ocr_fields = models.JSONField(
        default=dict,
        blank=True,
        help_text="Structured read of `ocr_text`: {patient_name, patient_phone, doctor_name, prescription_date, "
        "medications: [{name, strength, quantity, directions, duration, refills, medicine_id, catalog_name, "
        "match_confidence}], notes}. Each medication's name is reconciled against the medicine catalog server-side "
        "(medicine_id/catalog_name/match_confidence). Shown to the patient read-only on a paper upload and editable "
        "by a pharmacist on review. Empty when extraction is off or failed.",
    )
    ocr_provider = models.CharField(
        max_length=40, blank=True, help_text="Which extractor produced `ocr_fields` ('regex', 'openai_compatible', ...)."
    )
    ocr_review_requested = models.BooleanField(
        default=False, help_text="The patient flagged the OCR read as wrong; a pharmacist should re-check it before accepting."
    )
    ocr_review_note = models.CharField(max_length=500, blank=True, help_text="What the patient said was wrong with the OCR read.")
    ocr_confidence = models.FloatField(
        null=True,
        blank=True,
        help_text="0-1 reliability of the structured read: mostly the share of medication rows that "
        "linked to a real catalog SKU. Null when no extraction ran. Below "
        "OCR_LOW_CONFIDENCE_THRESHOLD the patient sees a 'a pharmacist will check your photo' "
        "notice instead of the parsed medication list, and scalar fields are not auto-filled from it.",
    )
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

    @property
    def effective_valid_until(self):
        if self.valid_until:
            return self.valid_until
        if self.prescription_date:
            return self.prescription_date + timedelta(days=settings.PRESCRIPTION_VALIDITY_DAYS)
        return None

    @property
    def is_expired(self) -> bool:
        """No prescription_date at all means age can't be verified - treat as expired."""
        expiry = self.effective_valid_until
        return expiry is None or timezone.localdate() > expiry

    @property
    def ocr_is_low_confidence(self) -> bool:
        """There is a structured read, but too weak to put in front of the patient as-is. A
        record with no extraction at all (`ocr_confidence` is None) is 'no read', not 'low
        confidence' - callers see that from `ocr_fields` being empty."""
        return self.ocr_confidence is not None and self.ocr_confidence < OCR_LOW_CONFIDENCE_THRESHOLD

