from django.conf import settings
from django.db import models

from apps.common.models import UUIDTimeStampedModel


def default_currency() -> str:
    return settings.PLATFORM_CURRENCY


class Payment(UUIDTimeStampedModel):
    """
    One payment per shopper order. `provider` picks the adapter (see
    apps.payments.providers) that actually talks to money — right now that's cash on
    delivery or a mock gateway standing in for whichever Lebanese payment platform
    (Whish Money, OMT, Areeba, ...) the team ends up integrating.
    """

    class Provider(models.TextChoices):
        CASH_ON_DELIVERY = "COD", "Cash on delivery"
        MOCK_GATEWAY = "MOCK_GATEWAY", "Card / wallet (demo gateway)"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PAID = "PAID", "Paid"
        FAILED = "FAILED", "Failed"
        REFUNDED = "REFUNDED", "Refunded"

    order = models.OneToOneField("orders.Order", on_delete=models.CASCADE, related_name="payment")
    provider = models.CharField(max_length=20, choices=Provider.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default=default_currency)
    external_reference = models.CharField(max_length=120, blank=True, help_text="The provider's own transaction id, once one exists.")
    paid_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.CharField(max_length=255, blank=True)
    raw_response = models.JSONField(null=True, blank=True, help_text="Provider payload, kept for reconciliation.")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.order.reference} - {self.provider} - {self.status}"
