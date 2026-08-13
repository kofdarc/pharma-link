from django.db import models
from django.utils import timezone

from apps.common.models import UUIDTimeStampedModel


class SubscriptionPlan(UUIDTimeStampedModel):
    """A tier a pharmacy can be put on: a flat monthly fee plus a per-request fee charged
    whenever the pharmacy accepts an order routed to it through the platform."""

    name = models.CharField(max_length=80, unique=True)
    monthly_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    service_fee_per_request = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["monthly_fee"]

    def __str__(self) -> str:
        return self.name


class PharmacySubscription(UUIDTimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        PAST_DUE = "PAST_DUE", "Past due"
        CANCELLED = "CANCELLED", "Cancelled"

    pharmacy = models.OneToOneField("pharmacies.Pharmacy", on_delete=models.CASCADE, related_name="subscription")
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    current_period_start = models.DateTimeField(default=timezone.now)
    current_period_end = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.pharmacy.name} - {self.plan.name}"


class PlatformServiceFee(UUIDTimeStampedModel):
    """
    One row per order request a pharmacy accepted - the unit the mentors' decided revenue
    model bills on ("service fees per request submitted through the platform").
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        INVOICED = "INVOICED", "Invoiced"
        PAID = "PAID", "Paid"
        WAIVED = "WAIVED", "Waived"

    pharmacy = models.ForeignKey("pharmacies.Pharmacy", on_delete=models.CASCADE, related_name="platform_service_fees", db_index=True)
    fulfillment = models.OneToOneField("orders.OrderFulfillment", on_delete=models.CASCADE, related_name="platform_service_fee")
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.pharmacy.name} - {self.amount}"
