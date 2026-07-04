from django.contrib.auth import authenticate
from rest_framework import serializers

from apps.accounts.models import User, UserRole
from apps.pharmacies.serializers import PharmacySerializer


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        user = authenticate(username=attrs["email"], password=attrs["password"])
        if not user:
            raise serializers.ValidationError("Invalid email or password.")
        if not user.is_active:
            raise serializers.ValidationError("This account is inactive.")
        if user.is_pharmacy_user and (not user.pharmacy_id or not user.pharmacy.is_active):
            raise serializers.ValidationError("This pharmacy account is inactive.")
        attrs["user"] = user
        return attrs


class UserSerializer(serializers.ModelSerializer):
    pharmacy_detail = PharmacySerializer(source="pharmacy", read_only=True)
    password = serializers.CharField(write_only=True, required=False, min_length=8)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "role",
            "pharmacy",
            "pharmacy_detail",
            "is_active",
            "created_at",
            "updated_at",
            "last_login_at",
            "password",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "last_login_at"]

    def validate(self, attrs):
        role = attrs.get("role", getattr(self.instance, "role", None))
        pharmacy = attrs.get("pharmacy", getattr(self.instance, "pharmacy", None))
        if role in {UserRole.PHARMACY_OWNER, UserRole.PHARMACY_STAFF} and not pharmacy:
            raise serializers.ValidationError({"pharmacy": "Pharmacy users must be assigned to a pharmacy."})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance

