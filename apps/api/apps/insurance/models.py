from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.common.models import UUIDTimeStampedModel


class InsuranceProvider(UUIDTimeStampedModel):
    """A third-party payer / TPA (GlobeMed, LibanCard, NexCare, MedNet, ...)."""

    name = models.CharField(max_length=160, unique=True)
    phone = models.CharField(max_length=40, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class InsurancePlan(UUIDTimeStampedModel):
    """
    A coverage tier under a provider. Coverage is plan-level percentage + a flat copay
    floor - no per-medicine formulary, matching most Lebanese employer/insurer plans and
    needing no formulary dataset the platform doesn't have.
    """

    provider = models.ForeignKey(InsuranceProvider, on_delete=models.CASCADE, related_name="plans")
    name = models.CharField(max_length=160)
    coverage_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))]
    )
    copay_minimum = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(Decimal("0"))])
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["provider__name", "name"]
        constraints = [models.UniqueConstraint(fields=["provider", "name"], name="unique_plan_name_per_provider")]

    def __str__(self) -> str:
        return f"{self.provider.name} - {self.name}"


class PatientInsurancePolicy(UUIDTimeStampedModel):
    """
    A policy card held by either a platform shopper (customer_user) or a pharmacy's own
    walk-in client record (client) - never both, so a walk-in never needs a login just to
    have insurance on file.
    """

    plan = models.ForeignKey(InsurancePlan, on_delete=models.PROTECT, related_name="policies")
    customer_user = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.CASCADE, related_name="insurance_policies"
    )
    client = models.ForeignKey(
        "customers.Client", null=True, blank=True, on_delete=models.CASCADE, related_name="insurance_policies"
    )
    member_id = models.CharField(max_length=80)
    holder_name = models.CharField(max_length=255)
    valid_until = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                check=(models.Q(customer_user__isnull=False) & models.Q(client__isnull=True))
                | (models.Q(customer_user__isnull=True) & models.Q(client__isnull=False)),
                name="policy_owner_xor_customer_user_client",
            )
        ]

    def __str__(self) -> str:
        return f"{self.holder_name} - {self.member_id}"

    @property
    def is_expired(self) -> bool:
        if not self.valid_until:
            return False
        from django.utils import timezone

        return self.valid_until < timezone.localdate()


class InsuranceClaim(UUIDTimeStampedModel):
    """
    One per dispensing event - a fulfillment (one pharmacy's slice of a platform order) or
    a counter sale, never per multi-pharmacy order, since each pharmacy submits its own
    claim to the TPA for what it actually dispensed. Adjudication is a manual tracker: no
    TPA in Lebanon exposes a shared real-time API, so staff record the outcome by hand, the
    same way cash-on-delivery payments are manually settled.
    """

    class Status(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Submitted"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        PAID = "PAID", "Paid"
        CANCELLED = "CANCELLED", "Cancelled"

    order_fulfillment = models.OneToOneField(
        "orders.OrderFulfillment", null=True, blank=True, on_delete=models.PROTECT, related_name="insurance_claim"
    )
    sale = models.OneToOneField("sales.Sale", null=True, blank=True, on_delete=models.PROTECT, related_name="insurance_claim")
    policy = models.ForeignKey(PatientInsurancePolicy, on_delete=models.PROTECT, related_name="claims")
    pharmacy = models.ForeignKey("pharmacies.Pharmacy", on_delete=models.PROTECT, related_name="insurance_claims", db_index=True)

    billed_amount = models.DecimalField(max_digits=12, decimal_places=2)
    covered_amount = models.DecimalField(max_digits=12, decimal_places=2)
    patient_copay = models.DecimalField(max_digits=12, decimal_places=2)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUBMITTED, db_index=True)
    approval_code = models.CharField(max_length=80, blank=True)
    rejection_reason = models.CharField(max_length=255, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["pharmacy", "status"])]
        constraints = [
            models.CheckConstraint(
                check=(models.Q(order_fulfillment__isnull=False) & models.Q(sale__isnull=True))
                | (models.Q(order_fulfillment__isnull=True) & models.Q(sale__isnull=False)),
                name="claim_source_xor_fulfillment_sale",
            )
        ]

    def __str__(self) -> str:
        return f"{self.policy.member_id} - {self.billed_amount} ({self.status})"
