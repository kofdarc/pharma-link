from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.common.models import UUIDTimeStampedModel


class InventoryBatch(UUIDTimeStampedModel):
    pharmacy = models.ForeignKey("pharmacies.Pharmacy", on_delete=models.PROTECT, related_name="inventory_batches", db_index=True)
    medicine = models.ForeignKey("medicines.Medicine", on_delete=models.PROTECT, related_name="inventory_batches", db_index=True)
    batch_number = models.CharField(max_length=120, blank=True)
    initial_quantity = models.PositiveIntegerField(default=0)
    current_quantity = models.PositiveIntegerField(default=0, db_index=True)
    # Units held for confirmed platform orders that have not yet been handed to a driver.
    reserved_quantity = models.PositiveIntegerField(default=0)
    expiry_date = models.DateField(null=True, blank=True, db_index=True)
    supplier_name = models.CharField(max_length=255, blank=True)
    purchase_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal("0"))])
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    low_stock_threshold = models.PositiveIntegerField(default=5)
    public_availability_enabled = models.BooleanField(default=True)
    is_archived = models.BooleanField(default=False)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="created_batches")
    updated_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="updated_batches")

    class Meta:
        indexes = [models.Index(fields=["pharmacy", "medicine", "expiry_date"])]

    @property
    def is_expired(self) -> bool:
        return bool(self.expiry_date and self.expiry_date < timezone.localdate())

    @property
    def is_expiring_soon(self) -> bool:
        if not self.expiry_date:
            return False
        delta = self.expiry_date - timezone.localdate()
        return 0 <= delta.days <= 60

    @property
    def available_quantity(self) -> int:
        """Sellable now: reserved units belong to orders already promised to a shopper."""
        return max(0, self.current_quantity - self.reserved_quantity)

    @property
    def is_low_stock(self) -> bool:
        return 0 < self.current_quantity <= self.low_stock_threshold

    def __str__(self) -> str:
        return f"{self.medicine} ({self.current_quantity})"


class StockMovement(UUIDTimeStampedModel):
    class MovementType(models.TextChoices):
        IMPORT = "IMPORT", "Import"
        MANUAL_ADJUSTMENT = "MANUAL_ADJUSTMENT", "Manual adjustment"
        SALE = "SALE", "Sale"
        RETURN = "RETURN", "Return"
        CORRECTION = "CORRECTION", "Correction"
        EXPIRED = "EXPIRED", "Expired"
        REMOVED = "REMOVED", "Removed"

    pharmacy = models.ForeignKey("pharmacies.Pharmacy", on_delete=models.PROTECT, related_name="stock_movements", db_index=True)
    inventory_batch = models.ForeignKey(InventoryBatch, on_delete=models.PROTECT, related_name="stock_movements")
    medicine = models.ForeignKey("medicines.Medicine", on_delete=models.PROTECT, related_name="stock_movements")
    movement_type = models.CharField(max_length=32, choices=MovementType.choices)
    quantity_delta = models.IntegerField()
    quantity_before = models.PositiveIntegerField()
    quantity_after = models.PositiveIntegerField()
    reason = models.TextField(blank=True)
    sale = models.ForeignKey("sales.Sale", null=True, blank=True, on_delete=models.PROTECT, related_name="stock_movements")
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="stock_movements")

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if self.quantity_after < 0:
            raise ValueError("Stock movement cannot leave negative quantity")
        if self.inventory_batch_id and self.pharmacy_id != self.inventory_batch.pharmacy_id:
            raise ValueError("Movement pharmacy must match batch pharmacy")
        super().save(*args, **kwargs)
