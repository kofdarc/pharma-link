import secrets

from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from apps.accounts.permissions import IsPharmacyOwner, IsPharmacyUserWithActivePharmacy
from apps.integrations.authentication import IntegrationKeyAuthentication
from apps.integrations.models import IntegrationKey, SkuMapping, SyncRun, WebhookEndpoint
from apps.integrations.permissions import HasIntegrationScope
from apps.integrations.serializers import (
    IntegrationKeyCreateSerializer,
    IntegrationKeySerializer,
    SalesSyncSerializer,
    SkuMappingSerializer,
    StockSyncSerializer,
    SyncRunSerializer,
    WebhookEndpointSerializer,
)
from apps.integrations.services.keys import create_integration_key, revoke_integration_key
from apps.integrations.services.sync import sync_sales, sync_stock
from apps.orders.models import OrderFulfillment
from apps.orders.serializers import PharmacyOrderFulfillmentSerializer
from apps.orders.services.lifecycle import FulfillmentError, accept_fulfillment, mark_ready, reject_fulfillment


class IntegrationKeyViewSet(ModelViewSet):
    """Pharmacy-owner only: these credentials can move stock."""

    serializer_class = IntegrationKeySerializer
    permission_classes = [IsPharmacyOwner]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        return IntegrationKey.objects.filter(pharmacy=self.request.user.pharmacy)

    def create(self, request, *args, **kwargs):
        serializer = IntegrationKeyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        key, secret = create_integration_key(
            pharmacy=request.user.pharmacy,
            user=request.user,
            name=serializer.validated_data.get("name") or "POS connector",
            scopes=serializer.validated_data.get("scopes"),
        )
        payload = IntegrationKeySerializer(key).data
        # Shown exactly once. There is no endpoint that can retrieve it again.
        payload["secret"] = secret
        payload["setup_hint"] = "Paste the key id and secret into the connector's config file. Store the secret in a password manager; it cannot be shown again."
        return Response(payload, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        revoke_integration_key(key=self.get_object(), user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SkuMappingViewSet(ModelViewSet):
    serializer_class = SkuMappingSerializer
    permission_classes = [IsPharmacyUserWithActivePharmacy]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        qs = SkuMapping.objects.filter(pharmacy=self.request.user.pharmacy).select_related("medicine")
        if self.request.query_params.get("unmapped") == "true":
            qs = qs.filter(medicine__isnull=True, is_ignored=False)
        search = self.request.query_params.get("q")
        if search:
            qs = qs.filter(Q(external_code__icontains=search) | Q(external_name__icontains=search))
        return qs

    def perform_create(self, serializer):
        serializer.save(pharmacy=self.request.user.pharmacy, match_method=SkuMapping.MatchMethod.MANUAL)

    def perform_update(self, serializer):
        method = SkuMapping.MatchMethod.MANUAL if "medicine" in serializer.validated_data else serializer.instance.match_method
        serializer.save(match_method=method)


class SyncRunViewSet(ReadOnlyModelViewSet):
    serializer_class = SyncRunSerializer
    permission_classes = [IsPharmacyUserWithActivePharmacy]

    def get_queryset(self):
        return SyncRun.objects.filter(pharmacy=self.request.user.pharmacy)


class WebhookEndpointViewSet(ModelViewSet):
    serializer_class = WebhookEndpointSerializer
    permission_classes = [IsPharmacyOwner]

    def get_queryset(self):
        return WebhookEndpoint.objects.filter(pharmacy=self.request.user.pharmacy)

    def perform_create(self, serializer):
        serializer.save(pharmacy=self.request.user.pharmacy, secret=secrets.token_urlsafe(24))


class OnboardingStatusView(APIView):
    """
    Drives the onboarding checklist. Each step is derived from real data rather than a
    manual flag, so a pharmacy cannot be 'onboarded' while its shelf is empty.
    """

    permission_classes = [IsPharmacyUserWithActivePharmacy]

    def get(self, request):
        pharmacy = request.user.pharmacy
        has_location = pharmacy.latitude is not None and pharmacy.longitude is not None
        stock_count = pharmacy.inventory_batches.filter(is_archived=False, current_quantity__gt=0).count()
        unmapped = SkuMapping.objects.filter(pharmacy=pharmacy, medicine__isnull=True, is_ignored=False).count()
        keys = IntegrationKey.objects.filter(pharmacy=pharmacy, is_active=True).count()
        last_sync = SyncRun.objects.filter(pharmacy=pharmacy).order_by("-created_at").first()
        steps = [
            {
                "key": "profile",
                "title": "Confirm pharmacy details and map location",
                "done": bool(has_location and pharmacy.phone),
                "hint": "A map pin is what lets the router quote a realistic delivery.",
            },
            {
                "key": "stock",
                "title": "Load stock (CSV/Excel import, manual, or connector)",
                "done": stock_count > 0,
                "detail": f"{stock_count} item(s) in stock",
                "hint": "Any of the three paths works; the connector keeps it current automatically.",
            },
            {
                "key": "mapping",
                "title": "Map your own product codes",
                "done": unmapped == 0,
                "detail": f"{unmapped} code(s) still unmapped",
                "hint": "One-time step per product code. After this your software syncs untouched.",
            },
            {
                "key": "connector",
                "title": "Issue an integration key for your software",
                "done": keys > 0,
                "detail": f"{keys} active key(s)",
            },
            {
                "key": "live",
                "title": "Go live for online orders",
                "done": bool(pharmacy.accepts_online_orders and stock_count > 0 and has_location),
            },
        ]
        return Response(
            {
                "pharmacy": pharmacy.name,
                "steps": steps,
                "completed_steps": sum(1 for step in steps if step["done"]),
                "total_steps": len(steps),
                "last_sync": SyncRunSerializer(last_sync).data if last_sync else None,
            }
        )


class IntegrationEndpoint(APIView):
    """Base for signature-authenticated machine endpoints."""

    authentication_classes = [IntegrationKeyAuthentication]
    permission_classes = [HasIntegrationScope]
    required_scope = ""

    @property
    def pharmacy(self):
        return self.request.user.pharmacy

    def sync_actor(self):
        """
        Stock movements need an accountable user. Integration writes are attributed to the
        pharmacy owner who issued the key, which keeps the audit trail meaningful.
        """
        return self.request.user.integration_key.created_by


class IntegrationPingView(IntegrationEndpoint):
    required_scope = IntegrationKey.Scope.ORDERS_READ

    def get(self, request):
        return Response(
            {
                "ok": True,
                "pharmacy": self.pharmacy.name,
                "key": request.user.integration_key.key_id,
                "scopes": request.user.integration_key.scopes,
                "server_time": timezone.now(),
            }
        )


class IntegrationStockSyncView(IntegrationEndpoint):
    required_scope = IntegrationKey.Scope.STOCK_WRITE

    def post(self, request):
        serializer = StockSyncSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        run = sync_stock(
            pharmacy=self.pharmacy,
            user=self.sync_actor(),
            rows=serializer.validated_data["rows"],
            integration_key=request.user.integration_key,
            idempotency_key=serializer.validated_data["idempotency_key"],
        )
        return Response(SyncRunSerializer(run).data, status=status.HTTP_200_OK if run.status == SyncRun.Status.REPLAYED else status.HTTP_201_CREATED)


class IntegrationSalesSyncView(IntegrationEndpoint):
    required_scope = IntegrationKey.Scope.SALES_WRITE

    def post(self, request):
        serializer = SalesSyncSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        run = sync_sales(
            pharmacy=self.pharmacy,
            user=self.sync_actor(),
            rows=serializer.validated_data["rows"],
            integration_key=request.user.integration_key,
            idempotency_key=serializer.validated_data["idempotency_key"],
        )
        return Response(SyncRunSerializer(run).data, status=status.HTTP_200_OK if run.status == SyncRun.Status.REPLAYED else status.HTTP_201_CREATED)


class IntegrationOrderListView(IntegrationEndpoint):
    required_scope = IntegrationKey.Scope.ORDERS_READ

    def get(self, request):
        qs = (
            OrderFulfillment.objects.filter(pharmacy=self.pharmacy)
            .select_related("order")
            .prefetch_related("lines__medicine")
            .order_by("-created_at")
        )
        if request.query_params.get("open", "true") == "true":
            qs = qs.filter(status__in=[OrderFulfillment.Status.PENDING, OrderFulfillment.Status.ACCEPTED, OrderFulfillment.Status.READY])
        return Response(PharmacyOrderFulfillmentSerializer(qs[:200], many=True).data)


class IntegrationOrderActionView(IntegrationEndpoint):
    required_scope = IntegrationKey.Scope.ORDERS_WRITE

    def post(self, request, pk, verb):
        fulfillment = OrderFulfillment.objects.filter(id=pk, pharmacy=self.pharmacy).first()
        if fulfillment is None:
            return Response({"detail": "Order not found."}, status=status.HTTP_404_NOT_FOUND)
        actor = self.sync_actor()
        try:
            if verb == "accept":
                fulfillment = accept_fulfillment(fulfillment=fulfillment, user=actor)
            elif verb == "reject":
                fulfillment = reject_fulfillment(fulfillment=fulfillment, user=actor, reason=request.data.get("reason", "Rejected by pharmacy software"))
            elif verb == "ready":
                fulfillment = mark_ready(fulfillment=fulfillment, user=actor)
            else:
                return Response({"detail": "Unknown action."}, status=status.HTTP_400_BAD_REQUEST)
        except FulfillmentError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(PharmacyOrderFulfillmentSerializer(fulfillment).data)
