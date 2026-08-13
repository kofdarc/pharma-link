from rest_framework import serializers

from apps.billing.models import PharmacySubscription, PlatformServiceFee, SubscriptionPlan


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = ["id", "name", "monthly_fee", "service_fee_per_request", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]


class PharmacySubscriptionSerializer(serializers.ModelSerializer):
    plan_detail = SubscriptionPlanSerializer(source="plan", read_only=True)
    pharmacy_name = serializers.CharField(source="pharmacy.name", read_only=True)

    class Meta:
        model = PharmacySubscription
        fields = ["id", "pharmacy", "pharmacy_name", "plan", "plan_detail", "status", "current_period_start", "current_period_end", "created_at"]
        read_only_fields = ["id", "pharmacy_name", "plan_detail", "created_at"]


class PlatformServiceFeeSerializer(serializers.ModelSerializer):
    pharmacy_name = serializers.CharField(source="pharmacy.name", read_only=True)
    order_reference = serializers.CharField(source="fulfillment.order.reference", read_only=True)

    class Meta:
        model = PlatformServiceFee
        fields = ["id", "pharmacy", "pharmacy_name", "fulfillment", "order_reference", "amount", "status", "created_at"]
        read_only_fields = fields
