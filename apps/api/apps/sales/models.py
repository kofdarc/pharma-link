from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.common.models import UUIDTimeStampedModel


class Sale(UUIDTimeStampedModel):
    class PaymentMethod(models.TextChoices):
        CASH = "CASH", "Cash"
        CARD = "CARD", "Card"
        ON_ACCOUNT = "ON_ACCOUNT", "On client account"
        OTHER = "OTHER", "Other"

    class Status(models.TextChoices):
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    class Channel(models.TextChoices):
        COUNTER = "COUNTER", "Counter"
        PLATFORM_ORDER = "PLATFORM_ORDER", "Platform order"
        INTEGRATION = "INTEGRATION", "Pharmacy software sync"

    invoice_number = models.CharField(max_length=40, unique=True)
    pharmacy = models.ForeignKey("pharmacies.Pharmacy", on_delete=models.PROTECT, related_name="sales", db_index=True)
    staff_user = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="sales")
    client = models.ForeignKey("customers.Client", null=True, blank=True, on_delete=models.PROTECT, related_name="sales", db_index=True)
    channel = models.CharField(max_length=20, choices=Channel.choices, default=Channel.COUNTER, db_index=True)
    sale_datetime = models.DateTimeField(default=timezone.now, db_index=True)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(Decimal("0"))])
    discount_total = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(Decimal("0"))])
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(Decimal("0"))])
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.COMPLETED)
    prescription_record = models.ForeignKey("prescriptions.PrescriptionRecord", null=True, blank=True, on_delete=models.SET_NULL, related_name="linked_sales")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-sale_datetime"]
        indexes = [models.Index(fields=["pharmacy", "sale_datetime"]), models.Index(fields=["pharmacy", "client"])]

    def __str__(self) -> str:
        return self.invoice_number


class SaleItem(UUIDTimeStampedModel):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
    medicine = models.ForeignKey("medicines.Medicine", on_delete=models.PROTECT, related_name="sale_items")
    inventory_batch = models.ForeignKey("inventory.InventoryBatch", null=True, blank=True, on_delete=models.PROTECT, related_name="sale_items")
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(Decimal("0"))])
    line_total = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])

    class Meta:
        ordering = ["created_at"]
