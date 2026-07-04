from rest_framework import serializers

from apps.pharmacies.models import Pharmacy


class PublicPharmacySerializer(serializers.ModelSerializer):
    class Meta:
        model = Pharmacy
        fields = ["id", "name", "address", "city", "area", "phone", "whatsapp", "email", "latitude", "longitude"]


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
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

