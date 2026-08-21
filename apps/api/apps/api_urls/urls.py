from django.urls import include, path
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.routers import DefaultRouter
from rest_framework.throttling import AnonRateThrottle

from apps.accounts.views import (
    AdminUserViewSet,
    LoginView,
    LogoutView,
    MeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    PharmacyStaffViewSet,
    ResendVerificationView,
    ShopperRegisterView,
    VerifyEmailView,
)
from apps.analytics.views import (
    AnalyticsDemandView,
    AnalyticsInventoryView,
    AnalyticsOverviewView,
    AnalyticsReplenishmentView,
    AnalyticsSalesView,
)
from apps.audit.views import AdminAuditLogViewSet, PharmacyAuditLogViewSet
from apps.billing.views import (
    AdminPharmacySubscriptionViewSet,
    AdminServiceFeeViewSet,
    AdminSubscriptionPlanViewSet,
    PharmacyServiceFeeViewSet,
    PharmacySubscriptionView,
    PlatformRevenueOverviewView,
)
from apps.customers.views import ClientViewSet
from apps.delivery.views import (
    AdminDriverViewSet,
    DispatchBoardView,
    DispatchPlanView,
    DispatchPreviewView,
    DriverPingView,
    DriverRouteViewSet,
    DriverSelfView,
    DriverStopActionView,
    OrderOfferView,
    RouteReoptimiseView,
)
from apps.eprescriptions.views import (
    AdminDoctorViewSet,
    DoctorActivationView,
    DoctorPrescriptionViewSet,
    DoctorProfileView,
    PharmacyPrescriptionScanView,
    prescription_qr,
    public_pharmacy_directory,
    public_prescription_dispense,
    public_prescription_lookup,
)
from apps.imports.views import AdminImportViewSet, PharmacyImportViewSet
from apps.integrations.views import (
    IntegrationKeyViewSet,
    IntegrationOrderActionView,
    IntegrationOrderListView,
    IntegrationPingView,
    IntegrationSalesSyncView,
    IntegrationStockSyncView,
    OnboardingStatusView,
    SkuMappingViewSet,
    SyncRunViewSet,
    WebhookEndpointViewSet,
)
from apps.inventory.services.availability import public_availability_search
from apps.inventory.views import InventoryBatchViewSet, ReservationShortfallViewSet, StockMovementViewSet
from apps.medicines.views import AdminMedicineViewSet, MedicineViewSet, medicine_search
from apps.orders.views import (
    AdminReviewViewSet,
    BasketQuoteView,
    DeliveryAddressViewSet,
    PharmacyOrderViewSet,
    RecurringOrderViewSet,
    ShopperOrderViewSet,
)
from apps.payments.views import AdminOrderRefundView, OrderPaymentView, PaymentMethodsView
from apps.pharmacies.views import (
    AdminPharmacyApplicationViewSet,
    AdminPharmacyViewSet,
    PharmacyApplicationSubmitView,
    PharmacyDashboardView,
    PharmacyProfileView,
    PublicPharmacyViewSet,
)
from apps.prescriptions.views import PrescriptionRecordViewSet
from apps.sales.views import SaleViewSet


class PublicSearchThrottle(AnonRateThrottle):
    scope = "public_search"


@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([PublicSearchThrottle])
def public_search(request):
    """
    Unified availability across all connected pharmacies. Ranked by distance, past shopper
    experience and reliability when coordinates are supplied; capped quantities only.
    """
    latitude = request.query_params.get("lat")
    longitude = request.query_params.get("lng")
    return Response(
        public_availability_search(
            query=request.query_params.get("q", ""),
            area=request.query_params.get("area", ""),
            medicine_id=request.query_params.get("medicine_id") or None,
            latitude=float(latitude) if latitude else None,
            longitude=float(longitude) if longitude else None,
            sort=request.query_params.get("sort", "best"),
            request=request,
        )
    )


router = DefaultRouter()
# Public / consumer
router.register("public/pharmacies", PublicPharmacyViewSet, basename="public-pharmacies")
router.register("shop/addresses", DeliveryAddressViewSet, basename="shop-addresses")
router.register("shop/orders", ShopperOrderViewSet, basename="shop-orders")
router.register("shop/recurring-orders", RecurringOrderViewSet, basename="shop-recurring-orders")

# Platform admin
router.register("admin/pharmacies", AdminPharmacyViewSet, basename="admin-pharmacies")
router.register("admin/pharmacy-applications", AdminPharmacyApplicationViewSet, basename="admin-pharmacy-applications")
router.register("admin/users", AdminUserViewSet, basename="admin-users")
router.register("admin/medicines", AdminMedicineViewSet, basename="admin-medicines")
router.register("admin/doctors", AdminDoctorViewSet, basename="admin-doctors")
router.register("admin/audit-logs", AdminAuditLogViewSet, basename="admin-audit-logs")
router.register("admin/imports", AdminImportViewSet, basename="admin-imports")
router.register("admin/drivers", AdminDriverViewSet, basename="admin-drivers")
router.register("admin/subscription-plans", AdminSubscriptionPlanViewSet, basename="admin-subscription-plans")
router.register("admin/pharmacy-subscriptions", AdminPharmacySubscriptionViewSet, basename="admin-pharmacy-subscriptions")
router.register("admin/service-fees", AdminServiceFeeViewSet, basename="admin-service-fees")
router.register("admin/reviews", AdminReviewViewSet, basename="admin-reviews")

# Pharmacy workspace
router.register("pharmacy/inventory", InventoryBatchViewSet, basename="pharmacy-inventory")
router.register("pharmacy/stock-movements", StockMovementViewSet, basename="pharmacy-stock-movements")
router.register("pharmacy/reservation-shortfalls", ReservationShortfallViewSet, basename="pharmacy-reservation-shortfalls")
router.register("pharmacy/imports", PharmacyImportViewSet, basename="pharmacy-imports")
router.register("pharmacy/sales", SaleViewSet, basename="pharmacy-sales")
router.register("pharmacy/invoices", SaleViewSet, basename="pharmacy-invoices")
router.register("pharmacy/clients", ClientViewSet, basename="pharmacy-clients")
router.register("pharmacy/prescriptions", PrescriptionRecordViewSet, basename="pharmacy-prescriptions")
router.register("pharmacy/orders", PharmacyOrderViewSet, basename="pharmacy-orders")
router.register("pharmacy/staff", PharmacyStaffViewSet, basename="pharmacy-staff")
router.register("pharmacy/audit-logs", PharmacyAuditLogViewSet, basename="pharmacy-audit-logs")
router.register("pharmacy/integration-keys", IntegrationKeyViewSet, basename="pharmacy-integration-keys")
router.register("pharmacy/sku-mappings", SkuMappingViewSet, basename="pharmacy-sku-mappings")
router.register("pharmacy/sync-runs", SyncRunViewSet, basename="pharmacy-sync-runs")
router.register("pharmacy/webhooks", WebhookEndpointViewSet, basename="pharmacy-webhooks")
router.register("pharmacy/service-fees", PharmacyServiceFeeViewSet, basename="pharmacy-service-fees")

# Doctors and drivers
router.register("doctor/prescriptions", DoctorPrescriptionViewSet, basename="doctor-prescriptions")
router.register("driver/routes", DriverRouteViewSet, basename="driver-routes")

router.register("medicines", MedicineViewSet, basename="medicines")

urlpatterns = [
    # Auth
    path("auth/login/", LoginView.as_view()),
    path("auth/logout/", LogoutView.as_view()),
    path("auth/me/", MeView.as_view()),
    path("auth/register/", ShopperRegisterView.as_view()),
    path("auth/password-reset/", PasswordResetRequestView.as_view()),
    path("auth/password-reset/confirm/", PasswordResetConfirmView.as_view()),
    path("auth/verify-email/", VerifyEmailView.as_view()),
    path("auth/verify-email/resend/", ResendVerificationView.as_view()),
    # Public
    path("public/search/", public_search),
    path("public/pharmacy-directory/", public_pharmacy_directory),
    path("public/pharmacy-applications/", PharmacyApplicationSubmitView.as_view()),
    path("public/rx/lookup/", public_prescription_lookup),
    path("public/rx/dispense/", public_prescription_dispense),
    # Shopper
    path("shop/quote/", BasketQuoteView.as_view()),
    path("shop/payment-methods/", PaymentMethodsView.as_view()),
    path("shop/orders/<uuid:pk>/pay/", OrderPaymentView.as_view()),
    path("admin/orders/<uuid:pk>/refund/", AdminOrderRefundView.as_view()),
    # Doctors
    path("doctors/activate/", DoctorActivationView.as_view()),
    path("doctor/profile/", DoctorProfileView.as_view()),
    path("doctor/prescriptions/<uuid:pk>/qr.svg", prescription_qr),
    # Pharmacy
    path("pharmacy/dashboard/", PharmacyDashboardView.as_view()),
    path("pharmacy/profile/", PharmacyProfileView.as_view()),
    path("pharmacy/rx/scan/", PharmacyPrescriptionScanView.as_view()),
    path("pharmacy/onboarding/", OnboardingStatusView.as_view()),
    path("pharmacy/subscription/", PharmacySubscriptionView.as_view()),
    path("pharmacy/analytics/overview/", AnalyticsOverviewView.as_view()),
    path("pharmacy/analytics/inventory/", AnalyticsInventoryView.as_view()),
    path("pharmacy/analytics/sales/", AnalyticsSalesView.as_view()),
    path("pharmacy/analytics/replenishment/", AnalyticsReplenishmentView.as_view()),
    path("pharmacy/analytics/demand/", AnalyticsDemandView.as_view()),
    # Platform revenue
    path("admin/revenue/overview/", PlatformRevenueOverviewView.as_view()),
    # Dispatch (platform operations)
    path("dispatch/board/", DispatchBoardView.as_view()),
    path("dispatch/plan/", DispatchPlanView.as_view()),
    path("dispatch/preview/", DispatchPreviewView.as_view()),
    path("dispatch/orders/<uuid:pk>/offers/", OrderOfferView.as_view()),
    path("dispatch/routes/<uuid:pk>/reoptimise/", RouteReoptimiseView.as_view()),
    # Driver
    path("driver/me/", DriverSelfView.as_view()),
    path("driver/ping/", DriverPingView.as_view()),
    path("driver/stops/<uuid:pk>/<str:verb>/", DriverStopActionView.as_view()),
    # Medicines
    path("medicines/search/", medicine_search),
    # Integration bridge (signed machine-to-machine)
    path("integration/v1/ping/", IntegrationPingView.as_view()),
    path("integration/v1/stock/sync/", IntegrationStockSyncView.as_view()),
    path("integration/v1/sales/sync/", IntegrationSalesSyncView.as_view()),
    path("integration/v1/orders/", IntegrationOrderListView.as_view()),
    path("integration/v1/orders/<uuid:pk>/<str:verb>/", IntegrationOrderActionView.as_view()),
    path("", include(router.urls)),
]
