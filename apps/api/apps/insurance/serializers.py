from rest_framework import serializers

from apps.insurance.models import InsuranceClaim, InsurancePlan, InsuranceProvider, PatientInsurancePolicy


class InsuranceProviderSerializer(serializers.ModelSerializer):
    class Meta:
        model = InsuranceProvider
        fields = ["id", "name", "phone", "notes", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]


class InsurancePlanSerializer(serializers.ModelSerializer):
    provider_name = serializers.CharField(source="provider.name", read_only=True)

    class Meta:
        model = InsurancePlan
        fields = ["id", "provider", "provider_name", "name", "coverage_percentage", "copay_minimum", "is_active", "created_at"]
        read_only_fields = ["id", "provider_name", "created_at"]


class PublicInsurancePlanSerializer(serializers.ModelSerializer):
    provider_name = serializers.CharField(source="provider.name", read_only=True)

    class Meta:
        model = InsurancePlan
        fields = ["id", "provider_name", "name", "coverage_percentage", "copay_minimum"]
        read_only_fields = fields


class PatientInsurancePolicySerializer(serializers.ModelSerializer):
    plan_detail = InsurancePlanSerializer(source="plan", read_only=True)

    class Meta:
        model = PatientInsurancePolicy
        fields = [
            "id",
            "plan",
            "plan_detail",
            "customer_user",
            "client",
            "member_id",
            "holder_name",
            "valid_until",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "plan_detail", "customer_user", "client", "created_at"]


class InsuranceClaimSerializer(serializers.ModelSerializer):
    policy_detail = PatientInsurancePolicySerializer(source="policy", read_only=True)
    pharmacy_name = serializers.CharField(source="pharmacy.name", read_only=True)
    order_reference = serializers.CharField(source="order_fulfillment.order.reference", read_only=True, default="")
    invoice_number = serializers.CharField(source="sale.invoice_number", read_only=True, default="")

    class Meta:
        model = InsuranceClaim
        fields = [
            "id",
            "order_fulfillment",
            "sale",
            "order_reference",
            "invoice_number",
            "policy",
            "policy_detail",
            "pharmacy",
            "pharmacy_name",
            "billed_amount",
            "covered_amount",
            "patient_copay",
            "status",
            "approval_code",
            "rejection_reason",
            "approved_at",
            "paid_at",
            "created_at",
        ]
        read_only_fields = fields


class ClaimStatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=InsuranceClaim.Status.choices)
    approval_code = serializers.CharField(required=False, allow_blank=True, max_length=80)
    rejection_reason = serializers.CharField(required=False, allow_blank=True, max_length=255)
