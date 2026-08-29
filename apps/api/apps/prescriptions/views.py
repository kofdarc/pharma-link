from django.conf import settings
from django.http import FileResponse
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.accounts.permissions import IsPharmacyUserWithActivePharmacy, IsShopper
from apps.audit.services import write_audit_log
from apps.prescriptions.models import ALLOWED_PRESCRIPTION_MIME_TYPES, PrescriptionRecord
from apps.prescriptions.serializers import PrescriptionRecordSerializer, ShopPrescriptionUploadSerializer
from apps.prescriptions.services.extraction import extract_candidate_lines
from apps.prescriptions.services.ocr.base import OcrProviderError, UnsupportedFileType
from apps.prescriptions.services.ocr.registry import get_provider
from apps.prescriptions.services.quality import check_scan_bytes, rejection_message


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

    The record is created unattached (no `pharmacy`) and PENDING_REVIEW; a
    pharmacy claims and verifies it before it can back a dispense. OCR is
    deliberately not exposed here - that stays a pharmacy-side action.
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

