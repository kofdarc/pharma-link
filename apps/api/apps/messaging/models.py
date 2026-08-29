from django.db import models

from apps.common.models import UUIDTimeStampedModel


class Conversation(UUIDTimeStampedModel):
    """
    One thread per shopper<->pharmacy leg of an order, OR per prescription<->target-pharmacy
    pair (clinical communication). Anchored to OrderFulfillment rather than Order for the
    former, since an order can fan out across several pharmacies (see
    apps.orders.models.OrderFulfillment) - anchoring here is what makes "which pharmacy is
    the other party" unambiguous. Anchored to Prescription for the latter (only meaningful
    once a prescription has a target_pharmacy - see eprescriptions.models.Prescription).

    Exactly one of (order_fulfillment, prescription) is set, and correspondingly exactly one
    of (customer, doctor_user) - enforced by the constraints below, same XOR pattern as
    apps.insurance.models.PatientInsurancePolicy.
    """

    order_fulfillment = models.OneToOneField("orders.OrderFulfillment", null=True, blank=True, on_delete=models.CASCADE, related_name="conversation")
    prescription = models.OneToOneField("eprescriptions.Prescription", null=True, blank=True, on_delete=models.CASCADE, related_name="conversation")
    customer = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.CASCADE, related_name="conversations")
    doctor_user = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.CASCADE, related_name="prescription_conversations")
    pharmacy = models.ForeignKey("pharmacies.Pharmacy", on_delete=models.CASCADE, related_name="conversations")
    customer_phone = models.CharField(
        max_length=20,
        db_index=True,
        help_text="E.164 phone of the non-pharmacy party (shopper or doctor), snapshotted at creation so a later profile edit can't break inbound WhatsApp matching.",
    )
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-last_message_at", "-created_at"]
        constraints = [
            models.CheckConstraint(
                check=(models.Q(order_fulfillment__isnull=False) & models.Q(prescription__isnull=True))
                | (models.Q(order_fulfillment__isnull=True) & models.Q(prescription__isnull=False)),
                name="conversation_anchor_xor_fulfillment_prescription",
            )
        ]

    def __str__(self) -> str:
        return f"{self.order_fulfillment or self.prescription} conversation"


class Message(UUIDTimeStampedModel):
    class Direction(models.TextChoices):
        OUTBOUND = "OUTBOUND", "Sent from the app (pharmacy or doctor) to the other party's WhatsApp"
        INBOUND = "INBOUND", "Reply from the other party's WhatsApp"

    class Status(models.TextChoices):
        QUEUED = "QUEUED", "Queued"
        SENT = "SENT", "Sent"
        DELIVERED = "DELIVERED", "Delivered"
        READ = "READ", "Read"
        FAILED = "FAILED", "Failed"
        RECEIVED = "RECEIVED", "Received"

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    sender_user = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", help_text="Null for inbound (shopper via WhatsApp) messages."
    )
    direction = models.CharField(max_length=10, choices=Direction.choices)
    body = models.TextField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.QUEUED)
    provider_message_id = models.CharField(max_length=120, blank=True)
    failure_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.direction} message on {self.conversation_id}"


class WhatsAppNotification(UUIDTimeStampedModel):
    """A system-generated WhatsApp template send, separate from human chat threads."""

    class Kind(models.TextChoices):
        ORDER_UPDATE = "ORDER_UPDATE", "Order update"
        REFILL_REMINDER = "REFILL_REMINDER", "Refill reminder"
        PHARMACY_ALERT = "PHARMACY_ALERT", "Pharmacy alert"
        PRESCRIPTION_EXPIRY = "PRESCRIPTION_EXPIRY", "Prescription expiry"
        RENEWAL_DECISION = "RENEWAL_DECISION", "Renewal decision"
        PAYMENT_FAILURE = "PAYMENT_FAILURE", "Payment failure"

    class Status(models.TextChoices):
        QUEUED = "QUEUED", "Queued"
        SENT = "SENT", "Sent"
        DELIVERED = "DELIVERED", "Delivered"
        READ = "READ", "Read"
        FAILED = "FAILED", "Failed"

    kind = models.CharField(max_length=32, choices=Kind.choices, db_index=True)
    deduplication_key = models.CharField(max_length=180, unique=True)
    recipient_phone = models.CharField(max_length=20)
    template_name = models.CharField(max_length=120)
    language_code = models.CharField(max_length=16, default="en")
    body_parameters = models.JSONField(default=list)
    button_url_suffix = models.CharField(max_length=255, blank=True)
    fallback_body = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.QUEUED, db_index=True)
    provider_message_id = models.CharField(max_length=120, blank=True, db_index=True)
    failure_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.kind} to {self.recipient_phone}: {self.status}"
