from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models

from apps.common.models import UUIDTimeStampedModel


class InventoryImport(UUIDTimeStampedModel):
    class Status(models.TextChoices):
        UPLOADED = "UPLOADED", "Uploaded"
        PARSED = "PARSED", "Parsed"
        CONFIRMED = "CONFIRMED", "Confirmed"
        FAILED = "FAILED", "Failed"
        CANCELLED = "CANCELLED", "Cancelled"

    pharmacy = models.ForeignKey("pharmacies.Pharmacy", on_delete=models.PROTECT, related_name="inventory_imports", db_index=True)
    uploaded_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="inventory_imports")
    original_filename = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UPLOADED)
    total_rows = models.PositiveIntegerField(default=0)
    valid_rows = models.PositiveIntegerField(default=0)
    invalid_rows = models.PositiveIntegerField(default=0)
    matched_rows = models.PositiveIntegerField(default=0)
    unmatched_rows = models.PositiveIntegerField(default=0)
    created_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    error_summary = models.TextField(blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class InventoryImportRow(UUIDTimeStampedModel):
    class Status(models.TextChoices):
        VALID_MATCHED = "VALID_MATCHED", "Valid matched"
        VALID_UNMATCHED = "VALID_UNMATCHED", "Valid unmatched"
        INVALID = "INVALID", "Invalid"
        SKIPPED = "SKIPPED", "Skipped"
        IMPORTED = "IMPORTED", "Imported"

    inventory_import = models.ForeignKey(InventoryImport, on_delete=models.CASCADE, related_name="rows")
    row_number = models.PositiveIntegerField()
    raw_medicine_name = models.CharField(max_length=255)
    normalized_name = models.CharField(max_length=255, blank=True)
    matched_medicine = models.ForeignKey("medicines.Medicine", null=True, blank=True, on_delete=models.PROTECT, related_name="import_rows")
    match_confidence = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    quantity = models.IntegerField(null=True, blank=True)
    batch_number = models.CharField(max_length=120, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    supplier_name = models.CharField(max_length=255, blank=True)
    purchase_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal("0"))])
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal("0"))])
    status = models.CharField(max_length=20, choices=Status.choices)
    error_message = models.TextField(blank=True)
    price_note = models.TextField(blank=True, help_text="Set when the imported price was snapped to the MoPH regulated price.")
    raw_data = models.JSONField(default=dict)

    class Meta:
        ordering = ["row_number"]
        constraints = [models.UniqueConstraint(fields=["inventory_import", "row_number"], name="unique_row_per_inventory_import")]
