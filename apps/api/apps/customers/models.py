from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models.functions import Lower

from apps.common.models import UUIDTimeStampedModel


class Client(UUIDTimeStampedModel):
    """A pharmacy's own client record. Scoped to the pharmacy: clients are never shared across tenants."""

    pharmacy = models.ForeignKey("pharmacies.Pharmacy", on_delete=models.PROTECT, related_name="clients", db_index=True)
    full_name = models.CharField(max_length=255, db_index=True)
    phone = models.CharField(max_length=40, db_index=True)
    email = models.EmailField(blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    address = models.TextField(blank=True)
    area = models.CharField(max_length=120, blank=True)
    allergies = models.TextField(blank=True)
    chronic_conditions = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    insurance_provider = models.CharField(max_length=160, blank=True)
    insurance_number = models.CharField(max_length=80, blank=True)
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(Decimal("0"))])
    marketing_opt_in = models.BooleanField(default=False)
    # Set when a platform shopper account is recognised as this pharmacy's client.
    platform_user = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="pharmacy_client_records")
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="created_clients")

    class Meta:
        ordering = ["full_name"]
        indexes = [models.Index(fields=["pharmacy", "full_name"]), models.Index(fields=["pharmacy", "phone"])]
        constraints = [
            models.UniqueConstraint(Lower("phone"), "pharmacy", condition=models.Q(is_active=True), name="unique_active_client_phone_per_pharmacy"),
        ]

    def __str__(self) -> str:
        return f"{self.full_name} ({self.phone})"


class ClientLedgerEntry(UUIDTimeStampedModel):
    """Append-only account statement: charges raise the balance owed, payments lower it."""

    class EntryType(models.TextChoices):
        CHARGE = "CHARGE", "Charge"
        PAYMENT = "PAYMENT", "Payment"
        ADJUSTMENT = "ADJUSTMENT", "Adjustment"

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="ledger_entries")
    entry_type = models.CharField(max_length=20, choices=EntryType.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    sale = models.ForeignKey("sales.Sale", null=True, blank=True, on_delete=models.SET_NULL, related_name="ledger_entries")
    memo = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="client_ledger_entries")

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Ledger entries are append-only; post a correcting entry instead.")
        super().save(*args, **kwargs)
