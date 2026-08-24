from rest_framework import serializers

from apps.pharmacies.models import Pharmacy, PharmacyApplication


class PublicPharmacySerializer(serializers.ModelSerializer):
    class Meta:
        model = Pharmacy
        fields = ["id", "name", "address", "city", "area", "phone", "whatsapp", "email", "latitude", "longitude", "is_on_call"]


class PharmacySerializer(serializers.ModelSerializer):
    class Meta:
        model = Pharmacy
        fields = [
            "id",
            "name",
            "license_number",
            "address",
            "city",
            "area",
            "phone",
            "whatsapp",
            "email",
            "latitude",
            "longitude",
            "is_active",
            "is_public",
            "is_on_call",
            "pos_system",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class PharmacyApplicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = PharmacyApplication
        fields = [
            "id",
            "pharmacy_name",
            "owner_name",
            "email",
            "phone",
            "city",
            "area",
            "license_number",
            "message",
            "status",
            "review_note",
            "reviewed_at",
            "created_pharmacy",
            "created_at",
        ]
        read_only_fields = ["id", "status", "review_note", "reviewed_at", "created_pharmacy", "created_at"]


class PharmacyApplicationReviewSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, max_length=255)

