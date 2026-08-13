from rest_framework import serializers

from apps.customers.models import Client, ClientLedgerEntry


class ClientSerializer(serializers.ModelSerializer):
    balance_due = serializers.SerializerMethodField()

    class Meta:
        model = Client
        fields = [
            "id",
            "pharmacy",
            "full_name",
            "phone",
            "email",
            "date_of_birth",
            "address",
            "area",
            "allergies",
            "chronic_conditions",
            "notes",
            "insurance_provider",
            "insurance_number",
            "credit_limit",
            "marketing_opt_in",
            "platform_user",
            "is_active",
            "balance_due",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "pharmacy", "platform_user", "balance_due", "created_at", "updated_at"]

    def get_balance_due(self, obj):
        from apps.customers.services import client_balance

        return client_balance(obj)


class ClientLedgerEntrySerializer(serializers.ModelSerializer):
    created_by_email = serializers.EmailField(source="created_by.email", read_only=True)

    class Meta:
        model = ClientLedgerEntry
        fields = ["id", "client", "entry_type", "amount", "sale", "memo", "created_by", "created_by_email", "created_at"]
        read_only_fields = ["id", "client", "created_by", "created_by_email", "created_at"]

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Post a positive amount and choose the matching entry type.")
        return value
