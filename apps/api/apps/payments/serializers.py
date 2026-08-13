from rest_framework import serializers

from apps.payments.models import Payment


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ["id", "order", "provider", "status", "amount", "currency", "external_reference", "paid_at", "failure_reason", "created_at"]
        read_only_fields = fields
