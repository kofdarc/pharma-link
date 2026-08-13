from rest_framework import serializers

from apps.audit.models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    actor_email = serializers.EmailField(source="actor_user.email", read_only=True)
    pharmacy_name = serializers.CharField(source="pharmacy.name", read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "actor_user",
            "actor_email",
            "pharmacy",
            "pharmacy_name",
            "action",
            "entity_type",
            "entity_id",
            "summary",
            "before_data",
            "after_data",
            "ip_address",
            "created_at",
        ]
        read_only_fields = fields

