from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from apps.accounts.permissions import IsPharmacyUserWithActivePharmacy, IsPlatformAdmin
from apps.imports.models import InventoryImport
from apps.imports.serializers import ImportUploadSerializer, InventoryImportSerializer
from apps.imports.services.workflow import confirm_import, create_import_preview


class PharmacyImportViewSet(ReadOnlyModelViewSet):
    serializer_class = InventoryImportSerializer
    permission_classes = [IsPharmacyUserWithActivePharmacy]

    def get_queryset(self):
        return InventoryImport.objects.filter(pharmacy=self.request.user.pharmacy).prefetch_related("rows__matched_medicine")

    @action(detail=False, methods=["post"], url_path="upload")
    def upload(self, request):
        serializer = ImportUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        inventory_import = create_import_preview(uploaded_file=serializer.validated_data["file"], user=request.user)
        return Response(self.get_serializer(inventory_import).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        try:
            inventory_import = confirm_import(inventory_import=self.get_object(), user=request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(inventory_import).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        inventory_import = self.get_object()
        if inventory_import.status == InventoryImport.Status.CONFIRMED:
            return Response({"detail": "Confirmed imports cannot be cancelled."}, status=status.HTTP_400_BAD_REQUEST)
        inventory_import.status = InventoryImport.Status.CANCELLED
        inventory_import.save(update_fields=["status", "updated_at"])
        return Response(self.get_serializer(inventory_import).data)


class AdminImportViewSet(ReadOnlyModelViewSet):
    queryset = InventoryImport.objects.select_related("pharmacy", "uploaded_by").prefetch_related("rows").order_by("-created_at")
    serializer_class = InventoryImportSerializer
    permission_classes = [IsPlatformAdmin]

