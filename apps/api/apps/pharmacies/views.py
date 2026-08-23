from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from apps.accounts.permissions import IsPharmacyUserWithActivePharmacy, IsPlatformAdmin
from apps.audit.models import AuditLog
from apps.audit.services import write_audit_log
from apps.imports.models import InventoryImport
from apps.inventory.models import InventoryBatch
from apps.pharmacies.models import Pharmacy, PharmacyApplication
from apps.pharmacies.serializers import PharmacyApplicationReviewSerializer, PharmacyApplicationSerializer, PharmacySerializer, PublicPharmacySerializer
from apps.pharmacies.services import ApplicationError, approve_application, deactivate_pharmacy, reject_application
from apps.sales.models import Sale


class AdminPharmacyViewSet(ModelViewSet):
    queryset = Pharmacy.objects.all().order_by("name")
    serializer_class = PharmacySerializer
    permission_classes = [IsPlatformAdmin]

    def perform_update(self, serializer):
        was_active = serializer.instance.is_active
        pharmacy = serializer.save()
        if was_active and not pharmacy.is_active:
            deactivate_pharmacy(pharmacy=pharmacy, user=self.request.user)
            write_audit_log(
                actor_user=self.request.user,
                pharmacy=pharmacy,
                action="pharmacies.deactivated",
                entity_type="Pharmacy",
                entity_id=pharmacy.id,
                summary=f"Deactivated {pharmacy.name}",
            )


class PharmacyApplicationSubmitView(APIView):
    """Public: how a prospective pharmacy asks to join, since only a platform admin can
    create a Pharmacy directly."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PharmacyApplicationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        application = serializer.save()
        return Response(PharmacyApplicationSerializer(application).data, status=status.HTTP_201_CREATED)


class AdminPharmacyApplicationViewSet(ModelViewSet):
    queryset = PharmacyApplication.objects.order_by("-created_at")
    serializer_class = PharmacyApplicationSerializer
    permission_classes = [IsPlatformAdmin]
    http_method_names = ["get", "post", "head", "options"]

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        serializer = PharmacyApplicationReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            application = approve_application(application=self.get_object(), reviewer=request.user, note=serializer.validated_data.get("note", ""))
        except ApplicationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(application).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        serializer = PharmacyApplicationReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            application = reject_application(application=self.get_object(), reviewer=request.user, note=serializer.validated_data.get("note", ""))
        except ApplicationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(application).data)


class PublicPharmacyViewSet(ReadOnlyModelViewSet):
    serializer_class = PublicPharmacySerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return Pharmacy.objects.filter(is_active=True, is_public=True).order_by("name")


class PharmacyProfileView(APIView):
    permission_classes = [IsPharmacyUserWithActivePharmacy]

    def get(self, request):
        return Response(PharmacySerializer(request.user.pharmacy).data)

    def patch(self, request):
        allowed = {"address", "city", "area", "phone", "whatsapp", "email", "latitude", "longitude", "is_public", "is_on_call"}
        data = {key: value for key, value in request.data.items() if key in allowed}
        serializer = PharmacySerializer(request.user.pharmacy, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class PharmacyDashboardView(APIView):
    permission_classes = [IsPharmacyUserWithActivePharmacy]

    def get(self, request):
        pharmacy = request.user.pharmacy
        inventory = InventoryBatch.objects.filter(pharmacy=pharmacy, is_archived=False)
        low_stock = [batch for batch in inventory.select_related("medicine") if batch.is_low_stock]
        expiring = [batch for batch in inventory.select_related("medicine") if batch.is_expiring_soon]
        recent_sales = Sale.objects.filter(pharmacy=pharmacy).order_by("-sale_datetime")[:5]
        recent_imports = InventoryImport.objects.filter(pharmacy=pharmacy).order_by("-created_at")[:5]
        recent_audit = AuditLog.objects.filter(pharmacy=pharmacy).order_by("-created_at")[:5]
        return Response(
            {
                "metrics": {
                    "inventory_batches": inventory.count(),
                    "low_stock_count": len(low_stock),
                    "expiring_soon_count": len(expiring),
                    "sales_today": Sale.objects.filter(pharmacy=pharmacy, sale_datetime__date=timezone.localdate()).count(),
                },
                "low_stock": [
                    {"id": batch.id, "medicine": str(batch.medicine), "current_quantity": batch.current_quantity, "threshold": batch.low_stock_threshold}
                    for batch in low_stock[:8]
                ],
                "expiring_soon": [
                    {"id": batch.id, "medicine": str(batch.medicine), "expiry_date": batch.expiry_date, "current_quantity": batch.current_quantity}
                    for batch in expiring[:8]
                ],
                "recent_sales": [{"id": sale.id, "invoice_number": sale.invoice_number, "total": sale.total, "sale_datetime": sale.sale_datetime} for sale in recent_sales],
                "recent_imports": [{"id": item.id, "status": item.status, "created_count": item.created_count, "created_at": item.created_at} for item in recent_imports],
                "recent_audit": [{"id": log.id, "action": log.action, "summary": log.summary, "created_at": log.created_at} for log in recent_audit],
            }
        )
