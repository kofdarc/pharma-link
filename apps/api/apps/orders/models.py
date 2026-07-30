from datetime import timedelta
from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.common.models import UUIDTimeStampedModel


class DeliveryAddress(UUIDTimeStampedModel):
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="addresses")
    label = models.CharField(max_length=80, default="Home")
    contact_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=40)
    address = models.TextField()
    area = models.CharField(max_length=120, db_index=True)
    city = models.CharField(max_length=120)
    building_notes = models.CharField(max_length=255, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, validators=[MinValueValidator(-90), MaxValueValidator(90)])
    longitude = models.DecimalField(max_digits=9, decimal_places=6, validators=[MinValueValidator(-180), MaxValueValidator(180)])
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_default", "label"]

    def __str__(self) -> str:
        return f"{self.label} - {self.area}"


class Order(UUIDTimeStampedModel):
    """
    A single shopper basket. Lines may be sourced from several pharmacies, so the order
    fans out into one OrderFulfillment per pharmacy while staying one order to the shopper.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Awaiting pharmacy acceptance"
        SCHEDULED = "SCHEDULED", "Scheduled for later"
        CONFIRMED = "CONFIRMED", "Confirmed"
        READY = "READY", "Ready for pickup by driver"
        ASSIGNED = "ASSIGNED", "Assigned to a driver"
        IN_TRANSIT = "IN_TRANSIT", "In transit"
        DELIVERED = "DELIVERED", "Delivered"
        COLLECTED = "COLLECTED", "Collected in store"
        PARTIALLY_CANCELLED = "PARTIALLY_CANCELLED", "Partially cancelled"
        CANCELLED = "CANCELLED", "Cancelled"

    class FulfillmentType(models.TextChoices):
        DELIVERY = "DELIVERY", "Delivery"
        PICKUP = "PICKUP", "Store pickup"

    class Source(models.TextChoices):
        WEB = "WEB", "Web"
        RECURRING = "RECURRING", "Recurring schedule"

    reference = models.CharField(max_length=24, unique=True, db_index=True)
    customer = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="orders", db_index=True)
    fulfillment_type = models.CharField(max_length=20, choices=FulfillmentType.choices, default=FulfillmentType.DELIVERY)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PENDING, db_index=True)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.WEB)
    recurring_order = models.ForeignKey("orders.RecurringOrder", null=True, blank=True, on_delete=models.SET_NULL, related_name="generated_orders")
    prescription = models.ForeignKey("eprescriptions.Prescription", null=True, blank=True, on_delete=models.SET_NULL, related_name="orders")

    # Address is snapshotted so a later edit to the saved address cannot rewrite delivery history.
    contact_name = models.CharField(max_length=255)
    contact_phone = models.CharField(max_length=40)
    address = models.TextField(blank=True)
    area = models.CharField(max_length=120, blank=True, db_index=True)
    city = models.CharField(max_length=120, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    delivery_notes = models.CharField(max_length=255, blank=True)

    scheduled_for = models.DateTimeField(null=True, blank=True, db_index=True, help_text="When the shopper wants it. Null means as soon as possible.")
    window_minutes = models.PositiveIntegerField(default=120, help_text="Width of the acceptable delivery window around scheduled_for.")
    released_at = models.DateTimeField(null=True, blank=True, help_text="When a scheduled order entered the dispatch pool.")

    items_subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    delivery_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    cancelled_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "scheduled_for"]), models.Index(fields=["customer", "created_at"])]

    def __str__(self) -> str:
        return self.reference

    @property
    def window_start(self):
        if not self.scheduled_for:
            return None
        return self.scheduled_for - timedelta(minutes=self.window_minutes // 2)

    @property
    def window_end(self):
        if not self.scheduled_for:
            return None
        return self.scheduled_for + timedelta(minutes=self.window_minutes // 2)


class OrderFulfillment(UUIDTimeStampedModel):
    """The slice of an order that one pharmacy is responsible for."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        ACCEPTED = "ACCEPTED", "Accepted"
        READY = "READY", "Ready"
        PICKED_UP = "PICKED_UP", "Picked up"
        DELIVERED = "DELIVERED", "Delivered"
        COLLECTED = "COLLECTED", "Collected in store"
        REJECTED = "REJECTED", "Rejected"
        CANCELLED = "CANCELLED", "Cancelled"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="fulfillments")
    pharmacy = models.ForeignKey("pharmacies.Pharmacy", on_delete=models.PROTECT, related_name="order_fulfillments", db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    handover_code = models.CharField(max_length=8, help_text="Shown to the driver at pickup so stock only leaves against a real task.")
    accepted_at = models.DateTimeField(null=True, blank=True)
    ready_at = models.DateTimeField(null=True, blank=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.CharField(max_length=255, blank=True)
    sale = models.ForeignKey("sales.Sale", null=True, blank=True, on_delete=models.SET_NULL, related_name="order_fulfillments")

    class Meta:
        ordering = ["created_at"]
        constraints = [models.UniqueConstraint(fields=["order", "pharmacy"], name="unique_pharmacy_per_order")]

    def __str__(self) -> str:
        return f"{self.order.reference} @ {self.pharmacy.name}"


class OrderLine(UUIDTimeStampedModel):
    fulfillment = models.ForeignKey(OrderFulfillment, on_delete=models.CASCADE, related_name="lines")
    medicine = models.ForeignKey("medicines.Medicine", on_delete=models.PROTECT, related_name="order_lines")
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    line_total = models.DecimalField(max_digits=12, decimal_places=2)
    is_price_regulated = models.BooleanField(default=False)
    prescription_item = models.ForeignKey("eprescriptions.PrescriptionItem", null=True, blank=True, on_delete=models.SET_NULL, related_name="order_lines")

    class Meta:
        ordering = ["created_at"]


class StockReservation(UUIDTimeStampedModel):
    """
    Soft hold on specific batches. Held stock is invisible to other shoppers but still
    on the pharmacy's shelf, and expires automatically so an abandoned order cannot
    strand inventory.
    """

    order_line = models.ForeignKey(OrderLine, on_delete=models.CASCADE, related_name="reservations")
    inventory_batch = models.ForeignKey("inventory.InventoryBatch", on_delete=models.PROTECT, related_name="reservations")
    quantity = models.PositiveIntegerField()
    expires_at = models.DateTimeField(db_index=True)
    released_at = models.DateTimeField(null=True, blank=True)
    consumed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]

    @property
    def is_open(self) -> bool:
        return self.released_at is None and self.consumed_at is None


class RecurringOrder(UUIDTimeStampedModel):
    """Repeat prescriptions and chronic medication: the platform re-sources on every cycle."""

    customer = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="recurring_orders")
    address = models.ForeignKey(DeliveryAddress, on_delete=models.PROTECT, related_name="recurring_orders")
    label = models.CharField(max_length=120, default="Monthly refill")
    items = models.JSONField(default=list, help_text="[{medicine: uuid, quantity: int}] - re-sourced each cycle, so a closed pharmacy never blocks a refill.")
    interval_days = models.PositiveIntegerField(default=30, validators=[MinValueValidator(1)])
    preferred_hour = models.PositiveIntegerField(default=10, validators=[MaxValueValidator(23)])
    next_run_at = models.DateTimeField(db_index=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    occurrences_created = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)
    last_error = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["next_run_at"]

    def __str__(self) -> str:
        return f"{self.label} every {self.interval_days}d"


class PharmacyReview(UUIDTimeStampedModel):
    """Past experience signal that feeds the consumer ranking."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="reviews")
    pharmacy = models.ForeignKey("pharmacies.Pharmacy", on_delete=models.CASCADE, related_name="reviews", db_index=True)
    customer = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="pharmacy_reviews")
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(blank=True)
    was_complete = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["order", "pharmacy"], name="unique_review_per_order_pharmacy")]


class UnmetDemandSignal(UUIDTimeStampedModel):
    """
    Every search or basket the network could not satisfy. This is the data pharmacies
    cannot get from their own till: demand they never saw because they had no stock.
    """

    class Source(models.TextChoices):
        SEARCH = "SEARCH", "Public search"
        BASKET = "BASKET", "Basket sourcing"

    medicine = models.ForeignKey("medicines.Medicine", null=True, blank=True, on_delete=models.SET_NULL, related_name="unmet_demand")
    query_text = models.CharField(max_length=255, blank=True)
    area = models.CharField(max_length=120, blank=True, db_index=True)
    quantity_requested = models.PositiveIntegerField(default=1)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.SEARCH)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["medicine", "created_at"]), models.Index(fields=["area", "created_at"])]
