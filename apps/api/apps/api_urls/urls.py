from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.accounts.views import AdminUserViewSet, LoginView, LogoutView, MeView, PharmacyStaffViewSet
from apps.audit.views import AdminAuditLogViewSet, PharmacyAuditLogViewSet
from apps.imports.views import AdminImportViewSet, PharmacyImportViewSet
from apps.inventory.views import InventoryBatchViewSet, StockMovementViewSet
from apps.medicines.views import AdminMedicineViewSet, MedicineViewSet, medicine_search
from apps.pharmacies.views import AdminPharmacyViewSet, PharmacyDashboardView, PharmacyProfileView, PublicPharmacyViewSet
from apps.prescriptions.views import PrescriptionRecordViewSet
from apps.sales.views import SaleViewSet
from apps.inventory.services.availability import public_availability_search
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
def public_search(request):
    return Response(
        public_availability_search(
            query=request.query_params.get("q", ""),
            area=request.query_params.get("area", ""),
            medicine_id=request.query_params.get("medicine_id") or None,
        )
    )


router = DefaultRouter()
router.register("public/pharmacies", PublicPharmacyViewSet, basename="public-pharmacies")
router.register("admin/pharmacies", AdminPharmacyViewSet, basename="admin-pharmacies")
router.register("admin/users", AdminUserViewSet, basename="admin-users")
router.register("admin/medicines", AdminMedicineViewSet, basename="admin-medicines")
router.register("admin/audit-logs", AdminAuditLogViewSet, basename="admin-audit-logs")
router.register("admin/imports", AdminImportViewSet, basename="admin-imports")
router.register("pharmacy/inventory", InventoryBatchViewSet, basename="pharmacy-inventory")
router.register("pharmacy/stock-movements", StockMovementViewSet, basename="pharmacy-stock-movements")
router.register("pharmacy/imports", PharmacyImportViewSet, basename="pharmacy-imports")
router.register("pharmacy/sales", SaleViewSet, basename="pharmacy-sales")
router.register("pharmacy/invoices", SaleViewSet, basename="pharmacy-invoices")
router.register("pharmacy/prescriptions", PrescriptionRecordViewSet, basename="pharmacy-prescriptions")
router.register("pharmacy/staff", PharmacyStaffViewSet, basename="pharmacy-staff")
router.register("pharmacy/audit-logs", PharmacyAuditLogViewSet, basename="pharmacy-audit-logs")
router.register("medicines", MedicineViewSet, basename="medicines")

urlpatterns = [
    path("auth/login/", LoginView.as_view()),
    path("auth/logout/", LogoutView.as_view()),
    path("auth/me/", MeView.as_view()),
    path("public/search/", public_search),
    path("pharmacy/dashboard/", PharmacyDashboardView.as_view()),
    path("pharmacy/profile/", PharmacyProfileView.as_view()),
    path("medicines/search/", medicine_search),
    path("", include(router.urls)),
]

