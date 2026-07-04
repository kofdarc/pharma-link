from rest_framework import serializers

from apps.inventory.models import InventoryBatch, StockMovement
from apps.medicines.serializers import MedicineSerializer


class InventoryBatchSerializer(serializers.ModelSerializer):
    medicine_detail = MedicineSerializer(source="medicine", read_only=True)
    is_low_stock = serializers.BooleanField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    is_expiring_soon = serializers.BooleanField(read_only=True)

    class Meta:
        model = InventoryBatch
        fields = [
            "id",
            "pharmacy",
            "medicine",
            "medicine_detail",
            "batch_number",
            "initial_quantity",
            "current_quantity",
            "expiry_date",
            "supplier_name",
            "purchase_cost",
            "selling_price",
            "low_stock_threshold",
            "public_availability_enabled",
            "is_archived",
            "is_low_stock",
            "is_expired",
            "is_expiring_soon",
            "created_by",
            "updated_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "pharmacy", "current_quantity", "created_by", "updated_by", "created_at", "updated_at"]


class StockMovementSerializer(serializers.ModelSerializer):
    medicine_name = serializers.CharField(source="medicine.brand_name", read_only=True)
    batch_number = serializers.CharField(source="inventory_batch.batch_number", read_only=True)
    created_by_email = serializers.EmailField(source="created_by.email", read_only=True)

    class Meta:
        model = StockMovement
        fields = [
            "id",
            "inventory_batch",
            "batch_number",
            "medicine",
            "medicine_name",
            "movement_type",
            "quantity_delta",
            "quantity_before",
            "quantity_after",
            "reason",
            "sale",
            "created_by",
            "created_by_email",
            "created_at",
        ]
        read_only_fields = fields


class StockAdjustmentSerializer(serializers.Serializer):
    quantity_delta = serializers.IntegerField()
    reason = serializers.CharField(required=False, allow_blank=True)

