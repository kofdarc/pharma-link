from rest_framework import serializers

from apps.integrations.models import IntegrationKey, SkuMapping, SyncRun, WebhookEndpoint
from apps.medicines.serializers import MedicineSerializer


class IntegrationKeySerializer(serializers.ModelSerializer):
    class Meta:
        model = IntegrationKey
        fields = [
            "id",
            "name",
            "key_id",
            "secret_fingerprint",
            "scopes",
            "is_active",
            "last_used_at",
            "last_used_ip",
            "request_count",
            "revoked_at",
            "created_at",
        ]
        # The secret itself is intentionally absent: it is returned once, by the create endpoint.
        read_only_fields = fields


class IntegrationKeyCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    scopes = serializers.ListField(child=serializers.ChoiceField(choices=IntegrationKey.Scope.choices), required=False)


class SkuMappingSerializer(serializers.ModelSerializer):
    medicine_detail = MedicineSerializer(source="medicine", read_only=True)

    class Meta:
        model = SkuMapping
        fields = [
            "id",
            "external_code",
            "external_name",
            "medicine",
            "medicine_detail",
            "match_method",
            "match_confidence",
            "is_ignored",
            "last_seen_at",
            "created_at",
        ]
        read_only_fields = ["id", "medicine_detail", "match_confidence", "last_seen_at", "created_at"]


class SyncRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = SyncRun
        fields = [
            "id",
            "kind",
            "status",
            "idempotency_key",
            "rows_received",
            "rows_applied",
            "rows_unmapped",
            "rows_failed",
            "response_payload",
            "error_summary",
            "created_at",
        ]
        read_only_fields = fields


class WebhookEndpointSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookEndpoint
        fields = ["id", "url", "events", "is_active", "last_delivery_at", "consecutive_failures", "created_at"]
        read_only_fields = ["id", "last_delivery_at", "consecutive_failures", "created_at"]


class StockSyncRowSerializer(serializers.Serializer):
    external_code = serializers.CharField(max_length=120)
    name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    quantity = serializers.IntegerField(min_value=0)
    selling_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    purchase_cost = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    expiry_date = serializers.DateField(required=False, allow_null=True)
    supplier_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    low_stock_threshold = serializers.IntegerField(required=False, min_value=0)


class StockSyncSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=80)
    rows = StockSyncRowSerializer(many=True)

    def validate_rows(self, rows):
        if not rows:
            raise serializers.ValidationError("Send at least one row.")
        if len(rows) > 5000:
            raise serializers.ValidationError("Send at most 5000 rows per sync.")
        return rows


class SalesSyncLineSerializer(serializers.Serializer):
    external_code = serializers.CharField(max_length=120)
    name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    quantity = serializers.IntegerField(min_value=1)
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)


class SalesSyncRowSerializer(serializers.Serializer):
    reference = serializers.CharField(max_length=80, required=False, allow_blank=True)
    payment_method = serializers.CharField(max_length=20, required=False, allow_blank=True)
    items = SalesSyncLineSerializer(many=True)


class SalesSyncSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=80)
    rows = SalesSyncRowSerializer(many=True)

    def validate_rows(self, rows):
        if not rows:
            raise serializers.ValidationError("Send at least one sale.")
        return rows
