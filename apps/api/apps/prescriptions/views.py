from django.conf import settings
from django.http import FileResponse
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.accounts.permissions import IsPharmacyUserWithActivePharmacy
from apps.audit.services import write_audit_log
from apps.prescriptions.models import ALLOWED_PRESCRIPTION_MIME_TYPES, PrescriptionRecord
from apps.prescriptions.serializers import PrescriptionRecordSerializer
from apps.prescriptions.services.extraction import extract_candidate_lines
from apps.prescriptions.services.ocr.base import OcrProviderError, UnsupportedFileType
from apps.prescriptions.services.ocr.registry import get_provider


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

