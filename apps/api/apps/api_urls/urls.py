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
    NotificationPreferencesView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    PharmacyStaffViewSet,
    ResendVerificationView,
    ShopperLocationView,
    ShopperRegisterView,
    VerifyEmailView,
)
from apps.analytics.views import (
    AnalyticsDemandView,
    AnalyticsDigestView,
    AnalyticsInsightsView,
    AnalyticsInventoryView,
    AnalyticsOverviewView,
    AnalyticsReplenishmentView,
    AnalyticsSalesView,
)
from apps.assistant.views import AssistantChatView, AssistantSessionView
from apps.notifications.views import NotificationsView
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
    DoctorRenewalRequestViewSet,
    MyPrescriptionsView,
    PharmacyIncomingPrescriptionViewSet,
    PharmacyPrescriptionScanView,
    PharmacyRenewalRequestViewSet,
    prescription_qr,
    public_pharmacy_directory,
    public_prescription_dispense,
    public_prescription_lookup,
)
from apps.imports.views import AdminImportViewSet, PharmacyImportViewSet
from apps.insurance.views import (
    AdminInsuranceClaimViewSet,
    AdminInsurancePlanViewSet,
    AdminInsuranceProviderViewSet,
    PharmacyInsuranceClaimViewSet,
    PharmacyInsurancePolicyViewSet,
    ShopInsurancePolicyViewSet,
    doctor_formulary_lookup,
    public_insurance_plans,
)
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
from apps.messaging.views import (
    DoctorPrescriptionMessagesView,
    PharmacyFulfillmentMessagesView,
    PharmacyPrescriptionMessagesView,
    ShopperFulfillmentMessagesView,
    WhatsAppWebhookView,
)
from apps.orders.views import (
    AdminReviewViewSet,
    BasketQuoteView,
    DeliveryAddressViewSet,
    FulfillmentOptionsView,
    PharmacyOrderViewSet,
    RecurringOrderViewSet,
    ShopperOrderViewSet,
)
from apps.payments.views import AdminOrderRefundView, OrderPaymentView, PaymentMethodsView, SavedPaymentMethodViewSet
from apps.pharmacies.views import (
    AdminPharmacyApplicationViewSet,
    AdminPharmacyViewSet,
    PharmacyApplicationSubmitView,
    PharmacyDashboardView,
    PharmacyProfileView,
    PublicPharmacyViewSet,
)
from apps.prescriptions.views import ShopPrescriptionUploadViewSet
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
            same_composition_as=request.query_params.get("same_composition_as") or None,
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
router.register("shop/insurance-policies", ShopInsurancePolicyViewSet, basename="shop-insurance-policies")
router.register("shop/prescription-uploads", ShopPrescriptionUploadViewSet, basename="shop-prescription-uploads")
# The shopper's own saved cards/cash, distinct from shop/payment-methods/ below
# which lists the providers the platform supports.
router.register("shop/saved-payment-methods", SavedPaymentMethodViewSet, basename="shop-saved-payment-methods")

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
router.register("admin/insurance-providers", AdminInsuranceProviderViewSet, basename="admin-insurance-providers")
router.register("admin/insurance-plans", AdminInsurancePlanViewSet, basename="admin-insurance-plans")
router.register("admin/insurance-claims", AdminInsuranceClaimViewSet, basename="admin-insurance-claims")

# Pharmacy workspace
router.register("pharmacy/inventory", InventoryBatchViewSet, basename="pharmacy-inventory")
router.register("pharmacy/stock-movements", StockMovementViewSet, basename="pharmacy-stock-movements")
router.register("pharmacy/reservation-shortfalls", ReservationShortfallViewSet, basename="pharmacy-reservation-shortfalls")
router.register("pharmacy/imports", PharmacyImportViewSet, basename="pharmacy-imports")
router.register("pharmacy/sales", SaleViewSet, basename="pharmacy-sales")
router.register("pharmacy/invoices", SaleViewSet, basename="pharmacy-invoices")
router.register("pharmacy/clients", ClientViewSet, basename="pharmacy-clients")
router.register("pharmacy/orders", PharmacyOrderViewSet, basename="pharmacy-orders")
router.register("pharmacy/staff", PharmacyStaffViewSet, basename="pharmacy-staff")
router.register("pharmacy/audit-logs", PharmacyAuditLogViewSet, basename="pharmacy-audit-logs")
router.register("pharmacy/integration-keys", IntegrationKeyViewSet, basename="pharmacy-integration-keys")
router.register("pharmacy/sku-mappings", SkuMappingViewSet, basename="pharmacy-sku-mappings")
router.register("pharmacy/sync-runs", SyncRunViewSet, basename="pharmacy-sync-runs")
router.register("pharmacy/webhooks", WebhookEndpointViewSet, basename="pharmacy-webhooks")
router.register("pharmacy/service-fees", PharmacyServiceFeeViewSet, basename="pharmacy-service-fees")
router.register("pharmacy/insurance-policies", PharmacyInsurancePolicyViewSet, basename="pharmacy-insurance-policies")
router.register("pharmacy/insurance-claims", PharmacyInsuranceClaimViewSet, basename="pharmacy-insurance-claims")
router.register("pharmacy/incoming-prescriptions", PharmacyIncomingPrescriptionViewSet, basename="pharmacy-incoming-prescriptions")
router.register("pharmacy/renewal-requests", PharmacyRenewalRequestViewSet, basename="pharmacy-renewal-requests")

# Doctors and drivers
router.register("doctor/prescriptions", DoctorPrescriptionViewSet, basename="doctor-prescriptions")
router.register("doctor/renewal-requests", DoctorRenewalRequestViewSet, basename="doctor-renewal-requests")
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
    path("auth/notification-preferences/", NotificationPreferencesView.as_view()),
    # Opt-in "near me" origin. Under shop/ rather than auth/ because it is shopping context,
    # not credentials - see apps.common.location for how it is read.
    path("shop/location/", ShopperLocationView.as_view()),
    # In-app assistant (role-scoped; anonymous callers get the guest persona)
    path("assistant/session/", AssistantSessionView.as_view()),
    path("assistant/chat/", AssistantChatView.as_view()),
    # In-app notification feed (role-scoped, computed on read; polled by the web client)
    path("notifications/", NotificationsView.as_view()),
    # Public
    path("public/search/", public_search),
    path("public/pharmacy-directory/", public_pharmacy_directory),
    path("public/pharmacy-applications/", PharmacyApplicationSubmitView.as_view()),
    path("public/rx/lookup/", public_prescription_lookup),
    path("public/rx/dispense/", public_prescription_dispense),
    path("public/insurance-plans/", public_insurance_plans),
    path("public/whatsapp/webhook/", WhatsAppWebhookView.as_view()),
    # Shopper
    path("shop/quote/", BasketQuoteView.as_view()),
    path("shop/fulfillment-options/", FulfillmentOptionsView.as_view()),
    path("shop/prescriptions/mine/", MyPrescriptionsView.as_view()),
    path("shop/payment-methods/", PaymentMethodsView.as_view()),
    path("shop/orders/<uuid:pk>/pay/", OrderPaymentView.as_view()),
    path("shop/order-fulfillments/<uuid:pk>/messages/", ShopperFulfillmentMessagesView.as_view()),
    path("pharmacy/order-fulfillments/<uuid:pk>/messages/", PharmacyFulfillmentMessagesView.as_view()),
    path("pharmacy/prescriptions/<uuid:pk>/messages/", PharmacyPrescriptionMessagesView.as_view()),
    path("admin/orders/<uuid:pk>/refund/", AdminOrderRefundView.as_view()),
    # Doctors
    path("doctors/activate/", DoctorActivationView.as_view()),
    path("doctor/profile/", DoctorProfileView.as_view()),
    path("doctor/prescriptions/<uuid:pk>/qr.svg", prescription_qr),
    path("doctor/prescriptions/<uuid:pk>/messages/", DoctorPrescriptionMessagesView.as_view()),
    path("doctor/formulary/lookup/", doctor_formulary_lookup),
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
    path("pharmacy/analytics/insights/", AnalyticsInsightsView.as_view()),
    path("pharmacy/analytics/digest/", AnalyticsDigestView.as_view()),
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
