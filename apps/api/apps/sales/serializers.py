from decimal import Decimal

from rest_framework import serializers

from apps.medicines.serializers import MedicineSerializer
from apps.sales.models import Sale, SaleItem


class SaleItemSerializer(serializers.ModelSerializer):
    medicine_detail = MedicineSerializer(source="medicine", read_only=True)
    batch_number = serializers.CharField(source="inventory_batch.batch_number", read_only=True)

    class Meta:
        model = SaleItem
        fields = ["id", "medicine", "medicine_detail", "inventory_batch", "batch_number", "quantity", "unit_price", "discount", "line_total"]
        read_only_fields = ["id", "medicine_detail", "batch_number", "line_total"]


class SaleSerializer(serializers.ModelSerializer):
    items = SaleItemSerializer(many=True, read_only=True)
    staff_email = serializers.EmailField(source="staff_user.email", read_only=True)
    client_name = serializers.CharField(source="client.full_name", read_only=True, default="")

    class Meta:
        model = Sale
        fields = [
            "id",
            "invoice_number",
            "pharmacy",
            "staff_user",
            "staff_email",
            "client",
            "client_name",
            "channel",
            "sale_datetime",
            "subtotal",
            "discount_total",
            "total",
            "payment_method",
            "status",
            "prescription_record",
            "notes",
            "items",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class SaleCreateLineSerializer(serializers.Serializer):
    medicine = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0"), required=False)
    discount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0"), required=False, default=Decimal("0"))


class SaleCreateSerializer(serializers.Serializer):
    items = SaleCreateLineSerializer(many=True)
    payment_method = serializers.ChoiceField(choices=Sale.PaymentMethod.choices, required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    prescription_record_id = serializers.UUIDField(required=False)
    client = serializers.UUIDField(required=False, allow_null=True)

    def validate_items(self, items):
        if not items:
            raise serializers.ValidationError("At least one line item is required.")
        return items
