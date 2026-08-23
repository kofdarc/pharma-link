from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone

from apps.common.models import UUIDTimeStampedModel


class Doctor(UUIDTimeStampedModel):
    """
    Pre-loaded from the Order of Physicians roster. A doctor has no onboarding to do:
    the record already exists and they only claim it (see services.activation).
    """

    class Source(models.TextChoices):
        ORDER_OF_PHYSICIANS = "ORDER_OF_PHYSICIANS", "Order of Physicians roster"
        MANUAL = "MANUAL", "Manually added"

    license_number = models.CharField(max_length=60, unique=True, db_index=True)
    full_name = models.CharField(max_length=255, db_index=True)
    specialty = models.CharField(max_length=160, blank=True)
    email = models.EmailField(unique=True, db_index=True)
    phone = models.CharField(max_length=40, blank=True)
    clinic_name = models.CharField(max_length=255, blank=True)
    clinic_address = models.TextField(blank=True)
    clinic_area = models.CharField(max_length=120, blank=True)
    source = models.CharField(max_length=32, choices=Source.choices, default=Source.ORDER_OF_PHYSICIANS)
    roster_synced_at = models.DateTimeField(null=True, blank=True)
    user = models.OneToOneField("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="doctor_profile")
    is_activated = models.BooleanField(default=False)
    activated_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True, help_text="Cleared when the Order of Physicians suspends the licence.")

    class Meta:
        ordering = ["full_name"]

    def __str__(self) -> str:
        return f"Dr. {self.full_name} ({self.license_number})"


class Prescription(UUIDTimeStampedModel):
    """
    A prescription is consumable by ANY pharmacy, including pharmacies with no PharmaLink account.
    Security model:
      - `code` is the human-typeable identifier (safe to show, not sufficient on its own)
      - `secret_hash` stores only the SHA-256 of the high-entropy key embedded in the QR link
        (safe unsalted: 256 bits of entropy makes a precomputed table infeasible)
      - `pin_hash` stores only a salted PBKDF2 hash of the 6-digit PIN used for manual entry
        (the PIN's small space - a million values - needs salting+iteration, unlike the key)
    A database leak therefore does not expose any prescription content.
    """

    class Status(models.TextChoices):
        ISSUED = "ISSUED", "Issued"
        PARTIALLY_DISPENSED = "PARTIALLY_DISPENSED", "Partially dispensed"
        FULLY_DISPENSED = "FULLY_DISPENSED", "Fully dispensed"
        EXPIRED = "EXPIRED", "Expired"
        CANCELLED = "CANCELLED", "Cancelled"

    doctor = models.ForeignKey(Doctor, on_delete=models.PROTECT, related_name="prescriptions", db_index=True)
    target_pharmacy = models.ForeignKey(
        "pharmacies.Pharmacy",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="targeted_prescriptions",
        help_text="Set when the doctor sends directly to the patient's chosen pharmacy. Left blank for deferred transmission (patient carries the QR/PIN to any pharmacy).",
    )
    renewed_from = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="renewals", help_text="Set on the fresh prescription created when a renewal request is approved."
    )
    code = models.CharField(max_length=24, unique=True, db_index=True)
    secret_hash = models.CharField(max_length=64)
    pin_hash = models.CharField(max_length=128)
    patient_name = models.CharField(max_length=255)
    patient_email = models.EmailField(blank=True)
    patient_phone = models.CharField(max_length=40, blank=True)
    patient_date_of_birth = models.DateField(null=True, blank=True)
    diagnosis_note = models.TextField(blank=True, help_text="Free note for the dispensing pharmacist. Not a diagnosis service.")
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.ISSUED, db_index=True)
    issued_at = models.DateTimeField(default=timezone.now, db_index=True)
    valid_until = models.DateTimeField(db_index=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.CharField(max_length=255, blank=True)
    email_sent_at = models.DateTimeField(null=True, blank=True)
    failed_auth_count = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True, help_text="Set after repeated failed PIN attempts.")

    class Meta:
        ordering = ["-issued_at"]
        indexes = [models.Index(fields=["doctor", "issued_at"])]

    def __str__(self) -> str:
        return self.code

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.valid_until

    @property
    def is_locked(self) -> bool:
        return bool(self.locked_until and timezone.now() < self.locked_until)

    @property
    def is_consumable(self) -> bool:
        return self.status in {self.Status.ISSUED, self.Status.PARTIALLY_DISPENSED} and not self.is_expired

    def recompute_status(self) -> str:
        items = list(self.items.all())
        if self.status == self.Status.CANCELLED:
            return self.status
        if all(item.quantity_dispensed >= item.quantity_prescribed for item in items) and items:
            self.status = self.Status.FULLY_DISPENSED
        elif any(item.quantity_dispensed > 0 for item in items):
            self.status = self.Status.PARTIALLY_DISPENSED if not self.is_expired else self.Status.EXPIRED
        elif self.is_expired:
            self.status = self.Status.EXPIRED
        else:
            self.status = self.Status.ISSUED
        return self.status


class PrescriptionItem(UUIDTimeStampedModel):
    prescription = models.ForeignKey(Prescription, on_delete=models.CASCADE, related_name="items")
    # Catalog link is optional so a doctor can prescribe something not yet in the PharmaLink catalog.
    medicine = models.ForeignKey("medicines.Medicine", null=True, blank=True, on_delete=models.PROTECT, related_name="prescription_items")
    medicine_text = models.CharField(max_length=255, help_text="What the doctor wrote, kept verbatim.")
    quantity_prescribed = models.PositiveIntegerField()
    quantity_dispensed = models.PositiveIntegerField(default=0)
    unit = models.CharField(max_length=40, default="unit")
    dosage_instructions = models.CharField(max_length=255, blank=True)
    allow_generic_substitution = models.BooleanField(default=True)

    class Meta:
        ordering = ["created_at"]

    @property
    def quantity_remaining(self) -> int:
        return max(0, self.quantity_prescribed - self.quantity_dispensed)


class PrescriptionDispense(UUIDTimeStampedModel):
    """One consumption event. `pharmacy` is null for pharmacies that have no PharmaLink account."""

    prescription = models.ForeignKey(Prescription, on_delete=models.PROTECT, related_name="dispenses")
    pharmacy = models.ForeignKey("pharmacies.Pharmacy", null=True, blank=True, on_delete=models.SET_NULL, related_name="prescription_dispenses")
    pharmacy_name = models.CharField(max_length=255)
    pharmacist_name = models.CharField(max_length=255)
    pharmacist_license = models.CharField(max_length=80, blank=True)
    contact_phone = models.CharField(max_length=40, blank=True)
    dispensed_at = models.DateTimeField(default=timezone.now, db_index=True)
    notes = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-dispensed_at"]


class PrescriptionDispenseItem(UUIDTimeStampedModel):
    dispense = models.ForeignKey(PrescriptionDispense, on_delete=models.CASCADE, related_name="items")
    prescription_item = models.ForeignKey(PrescriptionItem, on_delete=models.PROTECT, related_name="dispense_items")
    quantity = models.PositiveIntegerField()
    substituted_with = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["created_at"]


class PrescriptionAccessLog(UUIDTimeStampedModel):
    """Append-only trail for every public touch of a prescription, successful or not."""

    class Action(models.TextChoices):
        VIEW = "VIEW", "Viewed"
        DISPENSE = "DISPENSE", "Dispensed"
        AUTH_FAILED = "AUTH_FAILED", "Authentication failed"
        LOCKED = "LOCKED", "Locked out"

    prescription = models.ForeignKey(Prescription, null=True, blank=True, on_delete=models.SET_NULL, related_name="access_logs")
    code_attempted = models.CharField(max_length=64, blank=True)
    action = models.CharField(max_length=20, choices=Action.choices)
    method = models.CharField(max_length=20, blank=True, help_text="QR or MANUAL")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    detail = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["prescription", "created_at"])]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Access logs are append-only")
        super().save(*args, **kwargs)


class PrescriptionRenewalRequest(UUIDTimeStampedModel):
    """
    A pharmacy asking the prescriber to renew a prescription it has legitimate contact with
    (see services.renewal for the access check). Approval issues a brand-new Prescription
    (same items, fresh code/secret/PIN) linked back via Prescription.renewed_from, rather than
    mutating the original - the original keeps its own immutable dispense history.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        DENIED = "DENIED", "Denied"

    prescription = models.ForeignKey(Prescription, on_delete=models.CASCADE, related_name="renewal_requests")
    requested_by_pharmacy = models.ForeignKey("pharmacies.Pharmacy", on_delete=models.CASCADE, related_name="renewal_requests")
    requested_by_user = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    note = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    response_note = models.TextField(blank=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    new_prescription = models.OneToOneField(Prescription, null=True, blank=True, on_delete=models.SET_NULL, related_name="renewal_request_source")

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["prescription", "status"])]

    def __str__(self) -> str:
        return f"Renewal request for {self.prescription.code} ({self.status})"
