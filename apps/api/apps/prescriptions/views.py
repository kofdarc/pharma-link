import logging
from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import F, Q
from django.http import FileResponse
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.accounts.permissions import IsPharmacyUserWithActivePharmacy, IsShopper
from apps.audit.services import write_audit_log
from apps.prescriptions.models import (
    ALLOWED_PRESCRIPTION_MIME_TYPES,
    OCR_LOW_CONFIDENCE_THRESHOLD,
    PrescriptionRecord,
    validate_prescription_file,
)
from apps.prescriptions.serializers import (
    PharmacyPrescriptionUploadSerializer,
    PrescriptionRecordSerializer,
    PrescriptionUploadFlagSerializer,
    ShopPrescriptionUploadSerializer,
)
from apps.prescriptions.services.extraction import extract_candidate_lines
from apps.prescriptions.services.ocr.base import OcrProviderError, UnsupportedFileType
from apps.prescriptions.services.ocr.registry import get_provider
from apps.prescriptions.services.ocr.vision_structured import render_text
from apps.prescriptions.services.quality import check_scan_bytes, rejection_message
from apps.prescriptions.services.structured import extract_structured, structured_from_vision

logger = logging.getLogger(__name__)

# Scalar columns kept in step with the structured OCR read, so existing surfaces that read
# PrescriptionRecord.doctor_name / patient_name / ... directly keep working on a patient
# upload that no longer collects them on a form.
_SCALAR_FROM_OCR = ("doctor_name", "patient_name", "patient_phone")


def ocr_and_structure(file_obj, mime_type: str):
    """OCR an open scan file with the configured provider and structure the result.

    Two pipelines land here. A ``supports_structured`` provider (the vision ones) reads the
    image straight into fields in one call - better on handwriting, because the page context
    that makes a scrawl legible is still available when the fields are filled in. Every other
    provider does pixels-to-text and hands that text to the configured NLP extractor.

    The structured call degrading falls back to the two-stage path rather than failing: a
    patient must never lose an upload because a gateway was down, and the provider's
    ``extract_text`` renders the same read as plain text anyway.

    Returns ``(ocr_text, StructuredResult)``, or ``None`` if OCR itself failed (provider
    down, unreadable format) - the caller decides how to degrade. Used by both the upload
    `preview` (nothing persisted) and `run_structured_extraction` (stores it on the record).
    """
    try:
        provider = get_provider(settings.PRESCRIPTION_OCR_PROVIDER)
    except ValueError:
        logger.warning("Unknown PRESCRIPTION_OCR_PROVIDER %r", settings.PRESCRIPTION_OCR_PROVIDER, exc_info=True)
        return None

    if getattr(provider, "supports_structured", False):
        try:
            file_obj.seek(0)
            raw = provider.extract_structured_fields(file_obj, mime_type=mime_type)
            return render_text(raw), structured_from_vision(raw, provider.code)
        except (OcrProviderError, UnsupportedFileType, ValueError, OSError):
            logger.warning(
                "Structured vision OCR failed on a prescription scan; falling back to text extraction", exc_info=True
            )

    try:
        file_obj.seek(0)
        ocr = provider.extract_text(file_obj, mime_type=mime_type)
    except (OcrProviderError, UnsupportedFileType, ValueError, OSError):
        logger.warning("OCR failed on a prescription scan", exc_info=True)
        return None
    return ocr.text, extract_structured(ocr.text)


def run_structured_extraction(record: PrescriptionRecord, *, actor_user) -> bool:
    """OCR a just-uploaded scan and store the structured read on the record.

    Best-effort: any failure (no file, OCR provider down, unreadable format) is logged and
    swallowed - the upload still stands and a pharmacist reviews the scan by hand regardless.
    Returns True only when ``ocr_fields`` was actually populated.
    """
    if not record.file:
        return False

    with record.file.open("rb") as file_obj:
        outcome = ocr_and_structure(file_obj, record.file_mime_type)
    if outcome is None:
        return False
    ocr_text, result = outcome

    record.ocr_text = ocr_text
    record.ocr_fields = result.fields
    record.ocr_provider = result.provider
    record.ocr_confidence = result.confidence
    updated = ["ocr_text", "ocr_fields", "ocr_provider", "ocr_confidence"]

    # Only carry the read into the scalar columns when the read is trustworthy. A weak read
    # (mangled handwriting) would otherwise pin a garbled prescriber name or a misparsed date
    # onto the record, where other surfaces treat it as fact. `[illegible]` is what the vision
    # OCR provider writes for a word it won't guess - never a value to store.
    if result.confidence >= OCR_LOW_CONFIDENCE_THRESHOLD:
        for column in _SCALAR_FROM_OCR:
            value = result.fields.get(column) or ""
            if not getattr(record, column) and value and "[illegible]" not in value.lower():
                setattr(record, column, value[:255])
                updated.append(column)
        if not record.prescription_date and result.fields.get("prescription_date"):
            try:
                record.prescription_date = date.fromisoformat(result.fields["prescription_date"])
                updated.append("prescription_date")
            except ValueError:
                pass

    record.save(update_fields=updated)
    write_audit_log(
        actor_user=actor_user,
        pharmacy=record.pharmacy,
        action="prescriptions.ocr_extracted",
        entity_type="PrescriptionRecord",
        entity_id=record.id,
        summary=f"Structured OCR read ({result.provider}) on prescription upload",
    )
    return not result.is_empty


class PrescriptionRecordViewSet(ModelViewSet):
    serializer_class = PrescriptionRecordSerializer
    permission_classes = [IsPharmacyUserWithActivePharmacy]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return PrescriptionRecord.objects.filter(pharmacy=self.request.user.pharmacy).select_related("sale", "created_by")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        file_obj = serializer.validated_data.get("file")
        if file_obj and getattr(file_obj, "content_type", "") not in ALLOWED_PRESCRIPTION_MIME_TYPES:
            return Response({"file": "Prescription file must be PDF, JPG, JPEG, or PNG."}, status=status.HTTP_400_BAD_REQUEST)
        record = serializer.save(
            pharmacy=request.user.pharmacy,
            created_by=request.user,
            file_original_name=file_obj.name if file_obj else "",
            file_mime_type=getattr(file_obj, "content_type", "") if file_obj else "",
            file_size=file_obj.size if file_obj else None,
        )
        write_audit_log(
            actor_user=request.user,
            pharmacy=request.user.pharmacy,
            action="prescriptions.created",
            entity_type="PrescriptionRecord",
            entity_id=record.id,
            summary="Created prescription record",
        )
        return Response(self.get_serializer(record).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        record = self.get_object()
        if not record.file:
            return Response({"detail": "Prescription file not found."}, status=status.HTTP_404_NOT_FOUND)
        write_audit_log(
            actor_user=request.user,
            pharmacy=request.user.pharmacy,
            action="prescriptions.downloaded",
            entity_type="PrescriptionRecord",
            entity_id=record.id,
            summary="Downloaded prescription file",
        )
        return FileResponse(record.file.open("rb"), as_attachment=True, filename=record.file_original_name or "prescription")

    @action(detail=True, methods=["post"])
    def extract(self, request, pk=None):
        """
        OCR the scan and return candidate drug/dose/quantity lines for a pharmacist to
        review - nothing here is added to a sale automatically (docs/AI_FEATURES.md §2).
        The OCR transcription is cached on first call; candidate matching against the
        catalog is cheap and deterministic, so it's always recomputed fresh.
        """
        record = self.get_object()
        if not record.file:
            return Response({"detail": "This prescription record has no file to read."}, status=status.HTTP_400_BAD_REQUEST)

        if not record.ocr_text:
            provider = get_provider(settings.PRESCRIPTION_OCR_PROVIDER)
            try:
                with record.file.open("rb") as file_obj:
                    result = provider.extract_text(file_obj, mime_type=record.file_mime_type)
            except UnsupportedFileType as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            except OcrProviderError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
            record.ocr_text = result.text
            record.save(update_fields=["ocr_text"])
            write_audit_log(
                actor_user=request.user,
                pharmacy=request.user.pharmacy,
                action="prescriptions.ocr_extracted",
                entity_type="PrescriptionRecord",
                entity_id=record.id,
                summary=f"Ran OCR ({provider.code}) on prescription scan",
            )

        candidates = extract_candidate_lines(record.ocr_text)
        return Response({"provider": settings.PRESCRIPTION_OCR_PROVIDER, "ocr_text": record.ocr_text, "candidates": candidates})


class ShopPrescriptionUploadViewSet(ModelViewSet):
    """A patient uploading a photo/scan of their own paper prescription.

    On upload the scan is OCR'd and read into structured fields (``ocr_fields`` -
    patient, prescriber, date, medications with directions/duration/refills). The
    patient sees that read-only and can `flag` it if the OCR got something wrong;
    they never edit it. The record is created unattached (no `pharmacy`) and
    PENDING_REVIEW; a pharmacy claims, corrects, and accepts or rejects it
    (PharmacyPrescriptionUploadViewSet) before it can back a dispense.
    """

    serializer_class = ShopPrescriptionUploadSerializer
    permission_classes = [IsShopper]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        return PrescriptionRecord.objects.filter(customer=self.request.user).order_by("-created_at")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        file_obj = serializer.validated_data["file"]

        if getattr(file_obj, "content_type", "") not in ALLOWED_PRESCRIPTION_MIME_TYPES:
            return Response({"file": "Prescription file must be a PDF, JPG, JPEG, or PNG."}, status=status.HTTP_400_BAD_REQUEST)

        file_obj.seek(0)
        findings = check_scan_bytes(file_obj.read(), mime_type=getattr(file_obj, "content_type", ""))
        file_obj.seek(0)
        if rejection := rejection_message(findings):
            return Response({"file": rejection, "quality_findings": findings}, status=status.HTTP_400_BAD_REQUEST)

        record = serializer.save(
            customer=request.user,
            created_by=request.user,
            pharmacy=None,
            status=PrescriptionRecord.UploadStatus.PENDING_REVIEW,
            quality_findings=findings,
            file_original_name=file_obj.name,
            file_mime_type=getattr(file_obj, "content_type", ""),
            file_size=file_obj.size,
        )
        write_audit_log(
            actor_user=request.user,
            action="prescriptions.patient_uploaded",
            entity_type="PrescriptionRecord",
            entity_id=record.id,
            summary="Patient uploaded a paper prescription",
        )

        run_structured_extraction(record, actor_user=request.user)
        record.refresh_from_db()
        return Response(self.get_serializer(record).data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        record = self.get_object()
        if record.status == PrescriptionRecord.UploadStatus.ACCEPTED:
            return Response(
                {"detail": "This upload has been accepted by a pharmacy and can no longer be removed."},
                status=status.HTTP_409_CONFLICT,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["get"])
    def file(self, request, pk=None):
        record = self.get_object()
        if not record.file:
            return Response({"detail": "This upload has no file."}, status=status.HTTP_404_NOT_FOUND)
        return FileResponse(record.file.open("rb"), as_attachment=True, filename=record.file_original_name or "prescription")

    @action(detail=False, methods=["post"])
    def preview(self, request):
        """Read a just-picked scan and return the structured fields for the patient to check
        *before* they upload. Nothing is stored - no PrescriptionRecord is created here, and
        the real POST re-runs OCR server-side, so the preview is a convenience, not the
        source of truth. If OCR is unavailable ``ocr_fields`` comes back null and the upload
        still works."""
        file_obj = request.data.get("file")
        if not file_obj or not hasattr(file_obj, "read"):
            return Response({"file": "Attach the prescription photo to read."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            validate_prescription_file(file_obj)
        except DjangoValidationError as exc:
            return Response({"file": exc.messages[0]}, status=status.HTTP_400_BAD_REQUEST)
        mime_type = getattr(file_obj, "content_type", "")
        if mime_type not in ALLOWED_PRESCRIPTION_MIME_TYPES:
            return Response({"file": "Prescription file must be a PDF, JPG, JPEG, or PNG."}, status=status.HTTP_400_BAD_REQUEST)

        outcome = ocr_and_structure(file_obj, mime_type)
        if outcome is None:
            return Response({"provider": "", "ocr_fields": None, "low_confidence": False})
        _text, result = outcome
        return Response(
            {
                "provider": result.provider,
                "ocr_fields": result.fields,
                "low_confidence": result.confidence < OCR_LOW_CONFIDENCE_THRESHOLD,
            }
        )

    @action(detail=True, methods=["post"])
    def flag(self, request, pk=None):
        """The patient says the OCR read is wrong. Records the flag (plus an optional note)
        for the reviewing pharmacy - it does not change the OCR fields, which stay a
        pharmacist's to correct."""
        record = self.get_object()
        if record.status != PrescriptionRecord.UploadStatus.PENDING_REVIEW:
            return Response(
                {"detail": "This upload has already been reviewed."}, status=status.HTTP_409_CONFLICT
            )

        payload = PrescriptionUploadFlagSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        note = payload.validated_data["note"].strip()

        record.ocr_review_requested = True
        record.ocr_review_note = note
        findings = list(record.quality_findings or [])
        findings.append(
            {"code": "patient_flagged_ocr", "message": note or "Patient flagged the scanned details as inaccurate.", "severity": "warn"}
        )
        record.quality_findings = findings
        record.save(update_fields=["ocr_review_requested", "ocr_review_note", "quality_findings"])
        write_audit_log(
            actor_user=request.user,
            action="prescriptions.ocr_flagged",
            entity_type="PrescriptionRecord",
            entity_id=record.id,
            summary="Patient flagged the OCR read for pharmacy review",
        )
        return Response(self.get_serializer(record).data)


class PharmacyPrescriptionUploadViewSet(ModelViewSet):
    """The pharmacy's queue of patient paper uploads. A pharmacist can correct the OCR
    read inline (PATCH ``ocr_fields`` and the scalar fields), then `accept` or `reject`.
    Editing or acting on an unattached upload claims it for this pharmacy."""

    serializer_class = PharmacyPrescriptionUploadSerializer
    permission_classes = [IsPharmacyUserWithActivePharmacy]
    http_method_names = ["get", "patch", "post", "head", "options"]

    def get_queryset(self):
        pharmacy = self.request.user.pharmacy
        return (
            PrescriptionRecord.objects.filter(customer__isnull=False)
            .filter(Q(pharmacy=pharmacy) | Q(pharmacy__isnull=True, status=PrescriptionRecord.UploadStatus.PENDING_REVIEW))
            .select_related("customer")
            # Patient-flagged first, then the weakest OCR reads (the ones a pharmacist has to
            # retype from the scan), then oldest. Records with no read at all sort last.
            .order_by("-ocr_review_requested", F("ocr_confidence").asc(nulls_last=True), "created_at")
        )

    def _claim(self, record):
        if record.pharmacy_id is None:
            record.pharmacy = self.request.user.pharmacy
            record.save(update_fields=["pharmacy"])

    def perform_update(self, serializer):
        record = serializer.save()
        self._claim(record)
        write_audit_log(
            actor_user=self.request.user,
            pharmacy=self.request.user.pharmacy,
            action="prescriptions.upload_edited",
            entity_type="PrescriptionRecord",
            entity_id=record.id,
            summary="Pharmacist corrected the OCR read on a patient upload",
        )

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        record = self.get_object()
        self._claim(record)
        record.status = PrescriptionRecord.UploadStatus.ACCEPTED
        record.ocr_review_requested = False
        record.save(update_fields=["status", "ocr_review_requested"])
        write_audit_log(
            actor_user=request.user,
            pharmacy=request.user.pharmacy,
            action="prescriptions.upload_accepted",
            entity_type="PrescriptionRecord",
            entity_id=record.id,
            summary="Accepted a patient prescription upload",
        )
        return Response(self.get_serializer(record).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        record = self.get_object()
        reason = str(request.data.get("reason", "")).strip()[:500]
        if not reason:
            return Response({"reason": "Say why this upload is being rejected."}, status=status.HTTP_400_BAD_REQUEST)
        self._claim(record)
        record.status = PrescriptionRecord.UploadStatus.REJECTED
        record.rejection_reason = reason
        record.ocr_review_requested = False
        record.save(update_fields=["status", "rejection_reason", "ocr_review_requested"])
        write_audit_log(
            actor_user=request.user,
            pharmacy=request.user.pharmacy,
            action="prescriptions.upload_rejected",
            entity_type="PrescriptionRecord",
            entity_id=record.id,
            summary="Rejected a patient prescription upload",
        )
        return Response(self.get_serializer(record).data)

    @action(detail=True, methods=["get"])
    def file(self, request, pk=None):
        record = self.get_object()
        if not record.file:
            return Response({"detail": "This upload has no file."}, status=status.HTTP_404_NOT_FOUND)
        return FileResponse(record.file.open("rb"), as_attachment=True, filename=record.file_original_name or "prescription")
