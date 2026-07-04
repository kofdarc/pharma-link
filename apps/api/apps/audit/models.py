from django.db import models

from apps.common.models import UUIDTimeStampedModel


class AuditLog(UUIDTimeStampedModel):
    actor_user = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_logs")
    pharmacy = models.ForeignKey("pharmacies.Pharmacy", null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_logs", db_index=True)
    action = models.CharField(max_length=120)
    entity_type = models.CharField(max_length=120)
    entity_id = models.CharField(max_length=120)
    summary = models.TextField()
    before_data = models.JSONField(null=True, blank=True)
    after_data = models.JSONField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["pharmacy", "created_at"])]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Audit logs are append-only")
        super().save(*args, **kwargs)
