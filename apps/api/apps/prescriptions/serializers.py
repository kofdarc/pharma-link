from rest_framework import serializers

from apps.prescriptions.models import PrescriptionRecord
from apps.prescriptions.services.nlp.base import MEDICATION_KEYS, STRUCTURED_KEYS
from apps.prescriptions.services.structured import annotate_catalog_match


class PrescriptionRecordSerializer(serializers.ModelSerializer):
    created_by_email = serializers.EmailField(source="created_by.email", read_only=True)
    file_name = serializers.CharField(source="file_original_name", read_only=True)
    download_url = serializers.SerializerMethodField()
    is_expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = PrescriptionRecord
        fields = [
            "id",
            "pharmacy",
            "sale",
            "patient_name",
            "patient_phone",
            "doctor_name",
            "prescription_date",
            "valid_until",
            "is_expired",
            "file",
            "file_name",
            "file_mime_type",
            "file_size",
            "notes",
            "created_by",
            "created_by_email",
            "download_url",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "pharmacy",
            "is_expired",
            "file_name",
            "file_mime_type",
            "file_size",
            "created_by",
            "created_by_email",
            "download_url",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {"file": {"write_only": True, "required": False}}

    def get_download_url(self, obj):
        return f"/api/pharmacy/prescriptions/{obj.id}/download/" if obj.file else None


def _clean_structured_fields(value) -> dict:
    """Coerce an incoming ``ocr_fields`` payload to the known shape - unknown keys dropped,
    medication rows reduced to the known columns, quantity/refills to int-or-null. The same
    guarantee apps.prescriptions.services.structured makes on the extraction side, applied
    again here because a pharmacist's edit is just as much an untrusted client payload.

    The catalog-match keys (medicine_id/catalog_name/match_confidence) a client sends are
    ignored and re-derived from the corrected name/strength, so fixing a misread drug name
    re-links it to the right SKU."""
    if not isinstance(value, dict):
        raise serializers.ValidationError("ocr_fields must be an object.")

    medications = []
    raw_meds = value.get("medications")
    if raw_meds is not None and not isinstance(raw_meds, list):
        raise serializers.ValidationError("ocr_fields.medications must be a list.")
    for entry in raw_meds or []:
        if not isinstance(entry, dict):
            continue
        med = {key: entry.get(key, "") for key in MEDICATION_KEYS}
        for key in ("name", "strength", "directions", "duration"):
            med[key] = str(med[key] or "").strip()[:200]
        med["quantity"] = _int_or_none(med["quantity"])
        med["refills"] = _int_or_none(med["refills"])
        medications.append(annotate_catalog_match(med))

    cleaned = {key: value.get(key, "") for key in STRUCTURED_KEYS}
    for key in ("patient_name", "patient_phone", "doctor_name", "prescription_date", "notes"):
        cleaned[key] = str(cleaned[key] or "").strip()[:500]
    cleaned["medications"] = medications
    return cleaned


def _int_or_none(value):
    try:
        return max(0, min(9999, int(value)))
    except (TypeError, ValueError):
        return None


class ShopPrescriptionUploadSerializer(serializers.ModelSerializer):
    """A patient's own upload of a paper prescription. No pharmacy/staff fields:
    the record is unattached until a pharmacy claims it. The OCR read (``ocr_fields``)
    is shown read-only - the patient confirms it or flags it, never edits it."""

    file_name = serializers.CharField(source="file_original_name", read_only=True)
    download_url = serializers.SerializerMethodField()
    quality_warnings = serializers.SerializerMethodField()
    is_expired = serializers.BooleanField(read_only=True)
    # True when a read exists but is too weak to show the patient as a medication list - the
    # UI shows a "a pharmacist will check your photo" notice instead. See
    # PrescriptionRecord.ocr_is_low_confidence.
    ocr_low_confidence = serializers.BooleanField(source="ocr_is_low_confidence", read_only=True)

    class Meta:
        model = PrescriptionRecord
        fields = [
            "id",
            "status",
            "doctor_name",
            "prescription_date",
            "notes",
            "rejection_reason",
            "ocr_fields",
            "ocr_confidence",
            "ocr_low_confidence",
            "ocr_review_requested",
            "ocr_review_note",
            "file",
            "file_name",
            "file_mime_type",
            "file_size",
            "is_expired",
            "quality_warnings",
            "download_url",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "doctor_name",
            "prescription_date",
            "rejection_reason",
            "ocr_fields",
            "ocr_confidence",
            "ocr_low_confidence",
            "ocr_review_requested",
            "ocr_review_note",
            "file_name",
            "file_mime_type",
            "file_size",
            "is_expired",
            "quality_warnings",
            "download_url",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {"file": {"write_only": True, "required": True}}

    def get_download_url(self, obj):
        return f"/api/shop/prescription-uploads/{obj.id}/file/" if obj.file else None

    def get_quality_warnings(self, obj):
        return [f["message"] for f in (obj.quality_findings or []) if f.get("severity") == "warn"]


class PrescriptionUploadFlagSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=500, allow_blank=True, required=False, default="")


class PharmacyPrescriptionUploadSerializer(serializers.ModelSerializer):
    """The pharmacy-review view of a patient's paper upload. ``ocr_fields`` is writable
    here - a pharmacist corrects the OCR read inline rather than only accepting or
    rejecting it wholesale."""

    file_name = serializers.CharField(source="file_original_name", read_only=True)
    download_url = serializers.SerializerMethodField()
    quality_warnings = serializers.SerializerMethodField()
    customer_email = serializers.EmailField(source="customer.email", read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    ocr_low_confidence = serializers.BooleanField(source="ocr_is_low_confidence", read_only=True)

    class Meta:
        model = PrescriptionRecord
        fields = [
            "id",
            "status",
            "customer_email",
            "patient_name",
            "patient_phone",
            "doctor_name",
            "prescription_date",
            "valid_until",
            "notes",
            "rejection_reason",
            "ocr_fields",
            "ocr_text",
            "ocr_provider",
            "ocr_confidence",
            "ocr_low_confidence",
            "ocr_review_requested",
            "ocr_review_note",
            "quality_warnings",
            "is_expired",
            "file_name",
            "file_mime_type",
            "file_size",
            "download_url",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "customer_email",
            "ocr_text",
            "ocr_provider",
            "ocr_confidence",
            "ocr_low_confidence",
            "ocr_review_requested",
            "ocr_review_note",
            "quality_warnings",
            "is_expired",
            "file_name",
            "file_mime_type",
            "file_size",
            "download_url",
            "created_at",
            "updated_at",
        ]

    def validate_ocr_fields(self, value):
        return _clean_structured_fields(value)

    def get_download_url(self, obj):
        return f"/api/pharmacy/prescription-uploads/{obj.id}/file/" if obj.file else None

    def get_quality_warnings(self, obj):
        return [f["message"] for f in (obj.quality_findings or []) if f.get("severity") == "warn"]
