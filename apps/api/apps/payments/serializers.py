from django.utils.translation import gettext as _
from rest_framework import serializers

from apps.payments.models import Payment, SavedPaymentMethod


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ["id", "order", "provider", "status", "amount", "currency", "external_reference", "paid_at", "failure_reason", "created_at"]
        read_only_fields = fields


class SavedPaymentMethodSerializer(serializers.ModelSerializer):
    label = serializers.SerializerMethodField()

    class Meta:
        model = SavedPaymentMethod
        fields = ["id", "kind", "brand", "last4", "expiry", "is_default", "label", "created_at"]
        read_only_fields = ["id", "label", "created_at"]

    def get_label(self, obj) -> str:
        return str(obj)

    def validate(self, attrs):
        kind = attrs.get("kind", getattr(self.instance, "kind", None))
        if kind == SavedPaymentMethod.Kind.CARD:
            # A card the shopper cannot tell apart from another card is not
            # worth saving, so the recognisable half is required.
            for field in ("brand", "last4", "expiry"):
                if not (attrs.get(field) or getattr(self.instance, field, "")):
                    raise serializers.ValidationError({field: _("Required for a saved card.")})
            last4 = attrs.get("last4", getattr(self.instance, "last4", ""))
            if last4 and (len(last4) != 4 or not last4.isdigit()):
                raise serializers.ValidationError({"last4": _("Enter exactly the last four digits.")})
        else:
            # Cash carries no card detail; silently drop anything sent.
            attrs.update({"brand": "", "last4": "", "expiry": ""})
        return attrs
