from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from apps.accounts.permissions import IsPharmacyUserWithActivePharmacy
from apps.audit.services import write_audit_log
from apps.inventory.models import InventoryBatch, StockMovement
from apps.inventory.serializers import InventoryBatchSerializer, StockAdjustmentSerializer, StockMovementSerializer
from apps.inventory.services.stock import adjust_stock, create_inventory_batch


class InventoryBatchViewSet(ModelViewSet):
    serializer_class = InventoryBatchSerializer
    permission_classes = [IsPharmacyUserWithActivePharmacy]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        qs = InventoryBatch.objects.filter(pharmacy=self.request.user.pharmacy).select_related("medicine", "created_by", "updated_by").order_by("medicine__brand_name")
        search = self.request.query_params.get("q")
        if search:
            qs = qs.filter(Q(medicine__brand_name__icontains=search) | Q(medicine__generic_name__icontains=search) | Q(batch_number__icontains=search))
        if self.request.query_params.get("low_stock") == "true":
            qs = [batch.id for batch in qs if batch.is_low_stock]
            return InventoryBatch.objects.filter(id__in=qs).select_related("medicine")
        today = timezone.localdate()
        if self.request.query_params.get("expired") == "true":
            qs = qs.filter(expiry_date__lt=today)
        if self.request.query_params.get("expiring_soon") == "true":
            qs = qs.filter(expiry_date__gte=today, expiry_date__lte=today + timedelta(days=60))
        if self.request.query_params.get("public") == "true":
            qs = qs.filter(public_availability_enabled=True)
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        batch = create_inventory_batch(user=request.user, pharmacy=request.user.pharmacy, data=serializer.validated_data)
        return Response(self.get_serializer(batch).data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        previous_price = serializer.instance.selling_price
        batch = serializer.save(updated_by=self.request.user)
        if batch.selling_price != previous_price:
            write_audit_log(
                actor_user=self.request.user,
                pharmacy=batch.pharmacy,
                action="inventory.price_updated",
                entity_type="InventoryBatch",
                entity_id=batch.id,
                summary=f"Price for {batch.medicine} changed on batch {batch.batch_number}",
                before_data={"selling_price": str(previous_price)},
                after_data={"selling_price": str(batch.selling_price)},
            )

    @action(detail=True, methods=["post"])
    def adjust(self, request, pk=None):
        serializer = StockAdjustmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            batch = adjust_stock(batch_id=pk, user=request.user, **serializer.validated_data)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        return Response(self.get_serializer(batch).data)


class StockMovementViewSet(ReadOnlyModelViewSet):
    serializer_class = StockMovementSerializer
    permission_classes = [IsPharmacyUserWithActivePharmacy]

    def get_queryset(self):
        return StockMovement.objects.filter(pharmacy=self.request.user.pharmacy).select_related("medicine", "inventory_batch", "created_by")
