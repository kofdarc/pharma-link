from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from apps.accounts.permissions import IsPharmacyUserWithActivePharmacy, IsPlatformAdmin
from apps.audit.models import AuditLog
from apps.imports.models import InventoryImport
from apps.inventory.models import InventoryBatch
from apps.pharmacies.models import Pharmacy
from apps.pharmacies.serializers import PharmacySerializer, PublicPharmacySerializer
from apps.sales.models import Sale


class AdminPharmacyViewSet(ModelViewSet):
    queryset = Pharmacy.objects.all().order_by("name")
    serializer_class = PharmacySerializer
    permission_classes = [IsPlatformAdmin]


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
        allowed = {"address", "city", "area", "phone", "whatsapp", "email", "latitude", "longitude", "is_public"}
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
