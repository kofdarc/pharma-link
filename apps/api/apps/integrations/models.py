from django.db import models
from django.db.models.functions import Lower

from apps.common.models import UUIDTimeStampedModel


class IntegrationKey(UUIDTimeStampedModel):
    """
    Credentials for a pharmacy's own software (or the PharmaLink connector agent) to talk to
    the API without a human logging in.

    HMAC request signing is symmetric, so the server must be able to recover the secret.
    It is therefore stored ENCRYPTED (Fernet, key derived from DJANGO_SECRET_KEY) rather
    than hashed, is never returned by any endpoint, and is shown to the pharmacy exactly
    once at creation. `secret_fingerprint` lets support identify a key without revealing it.
    """

    class Scope(models.TextChoices):
        STOCK_WRITE = "stock:write", "Push stock levels"
        SALES_WRITE = "sales:write", "Push sales"
        ORDERS_READ = "orders:read", "Pull platform orders"
        ORDERS_WRITE = "orders:write", "Accept/reject platform orders"

    pharmacy = models.ForeignKey("pharmacies.Pharmacy", on_delete=models.CASCADE, related_name="integration_keys", db_index=True)
    name = models.CharField(max_length=120, default="POS connector")
    key_id = models.CharField(max_length=40, unique=True, db_index=True)
    secret_encrypted = models.TextField()
    secret_fingerprint = models.CharField(max_length=16, blank=True)
    scopes = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    last_used_ip = models.GenericIPAddressField(null=True, blank=True)
    request_count = models.PositiveIntegerField(default=0)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="created_integration_keys")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.key_id})"

    def has_scope(self, scope: str) -> bool:
        return scope in (self.scopes or [])


class RequestNonce(UUIDTimeStampedModel):
    """Replay protection: a signed request may be presented exactly once."""

    integration_key = models.ForeignKey(IntegrationKey, on_delete=models.CASCADE, related_name="nonces")
    nonce = models.CharField(max_length=80)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["integration_key", "nonce"], name="unique_nonce_per_key")]
        indexes = [models.Index(fields=["created_at"])]


class SkuMapping(UUIDTimeStampedModel):
    """
    The heart of smooth onboarding: a pharmacy keeps using its own product codes and we
    map them once. After that, syncs need no data cleanup on their side.
    """

    class MatchMethod(models.TextChoices):
        MANUAL = "MANUAL", "Confirmed by pharmacy"
        AUTO_EXACT = "AUTO_EXACT", "Exact catalog match"
        AUTO_FUZZY = "AUTO_FUZZY", "Fuzzy catalog match"
        UNMATCHED = "UNMATCHED", "Not matched yet"

    pharmacy = models.ForeignKey("pharmacies.Pharmacy", on_delete=models.CASCADE, related_name="sku_mappings", db_index=True)
    external_code = models.CharField(max_length=120, db_index=True)
    external_name = models.CharField(max_length=255, blank=True)
    medicine = models.ForeignKey("medicines.Medicine", null=True, blank=True, on_delete=models.PROTECT, related_name="sku_mappings")
    match_method = models.CharField(max_length=20, choices=MatchMethod.choices, default=MatchMethod.UNMATCHED)
    match_confidence = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    is_ignored = models.BooleanField(default=False, help_text="Set for the pharmacy's non-pharma lines that should never sync.")
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["external_name", "external_code"]
        constraints = [models.UniqueConstraint(Lower("external_code"), "pharmacy", name="unique_external_code_per_pharmacy")]

    def __str__(self) -> str:
        return f"{self.external_code} -> {self.medicine or 'unmapped'}"


class SyncRun(UUIDTimeStampedModel):
    """One inbound sync from a pharmacy's software. Idempotent on `idempotency_key`."""

    class Kind(models.TextChoices):
        STOCK = "STOCK", "Stock levels"
        SALES = "SALES", "Sales"

    class Status(models.TextChoices):
        APPLIED = "APPLIED", "Applied"
        PARTIAL = "PARTIAL", "Partially applied"
        REJECTED = "REJECTED", "Rejected"
        REPLAYED = "REPLAYED", "Duplicate, previous result returned"

    pharmacy = models.ForeignKey("pharmacies.Pharmacy", on_delete=models.CASCADE, related_name="sync_runs", db_index=True)
    integration_key = models.ForeignKey(IntegrationKey, null=True, blank=True, on_delete=models.SET_NULL, related_name="sync_runs")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.APPLIED)
    idempotency_key = models.CharField(max_length=80, db_index=True)
    rows_received = models.PositiveIntegerField(default=0)
    rows_applied = models.PositiveIntegerField(default=0)
    rows_unmapped = models.PositiveIntegerField(default=0)
    rows_failed = models.PositiveIntegerField(default=0)
    response_payload = models.JSONField(default=dict)
    error_summary = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["pharmacy", "idempotency_key"], name="unique_idempotency_key_per_pharmacy")]


class WebhookEndpoint(UUIDTimeStampedModel):
    """Push side of the bridge: we notify the pharmacy's software instead of it polling."""

    pharmacy = models.ForeignKey("pharmacies.Pharmacy", on_delete=models.CASCADE, related_name="webhook_endpoints")
    url = models.URLField()
    secret = models.CharField(max_length=80, help_text="Used to sign the payload so the receiver can verify it came from us.")
    events = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)
    last_delivery_at = models.DateTimeField(null=True, blank=True)
    consecutive_failures = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]


class WebhookDelivery(UUIDTimeStampedModel):
    endpoint = models.ForeignKey(WebhookEndpoint, on_delete=models.CASCADE, related_name="deliveries")
    event = models.CharField(max_length=60)
    payload = models.JSONField(default=dict)
    status_code = models.PositiveIntegerField(null=True, blank=True)
    error = models.CharField(max_length=255, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
