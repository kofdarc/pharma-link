from rest_framework import serializers

from apps.imports.models import InventoryImport, InventoryImportRow
from apps.medicines.serializers import MedicineSerializer


class InventoryImportRowSerializer(serializers.ModelSerializer):
    matched_medicine_detail = MedicineSerializer(source="matched_medicine", read_only=True)

    class Meta:
        model = InventoryImportRow
        fields = [
            "id",
            "row_number",
            "raw_medicine_name",
            "normalized_name",
            "matched_medicine",
            "matched_medicine_detail",
            "match_confidence",
            "quantity",
            "batch_number",
            "expiry_date",
            "supplier_name",
            "purchase_cost",
            "selling_price",
            "status",
            "error_message",
            "price_note",
            "raw_data",
        ]


class InventoryImportSerializer(serializers.ModelSerializer):
    rows = InventoryImportRowSerializer(many=True, read_only=True)

    class Meta:
        model = InventoryImport
        fields = [
            "id",
            "pharmacy",
            "uploaded_by",
            "original_filename",
            "status",
            "total_rows",
            "valid_rows",
            "invalid_rows",
            "matched_rows",
            "unmatched_rows",
            "created_count",
            "skipped_count",
            "error_summary",
            "confirmed_at",
            "created_at",
            "rows",
        ]
        read_only_fields = fields


class ImportUploadSerializer(serializers.Serializer):
    file = serializers.FileField()

