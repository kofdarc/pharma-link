from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.translation import gettext as _
from rest_framework import serializers

from apps.accounts.models import NotificationPreferences, ShopperLocation, User, UserRole
from apps.pharmacies.serializers import PharmacySerializer


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        user = authenticate(username=attrs["email"], password=attrs["password"])
        if not user:
            raise serializers.ValidationError(_("Invalid email or password."))
        if not user.is_active:
            raise serializers.ValidationError(_("This account is inactive."))
        if user.is_pharmacy_user and (not user.pharmacy_id or not user.pharmacy.is_active):
            raise serializers.ValidationError(_("This pharmacy account is inactive."))
        attrs["user"] = user
        return attrs


class ShopperRegisterSerializer(serializers.Serializer):
    """Self-service signup, shoppers only. Roles that carry authority are never self-assigned."""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(_("An account already exists for this email."))
        return value.lower()

    def validate_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value

    def create(self, validated_data):
        return User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            role=UserRole.CUSTOMER,
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
            is_active=True,
            email_verified=False,
        )


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(write_only=True, min_length=8)

    def validate_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value


class EmailVerificationConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()


class ResendVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField()


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
            "phone",
            "role",
            "pharmacy",
            "pharmacy_detail",
            "is_active",
            "email_verified",
            "created_at",
            "updated_at",
            "last_login_at",
            "password",
        ]
        read_only_fields = ["id", "email_verified", "created_at", "updated_at", "last_login_at"]

    def validate(self, attrs):
        role = attrs.get("role", getattr(self.instance, "role", None))
        pharmacy = attrs.get("pharmacy", getattr(self.instance, "pharmacy", None))
        if role in {UserRole.PHARMACY_OWNER, UserRole.PHARMACY_STAFF} and not pharmacy:
            raise serializers.ValidationError({"pharmacy": _("Pharmacy users must be assigned to a pharmacy.")})
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


class OwnProfileSerializer(serializers.ModelSerializer):
    """
    What a user may change about themselves.

    Narrower than UserSerializer on purpose: role, pharmacy, is_active and
    email_verified are decisions the platform makes about an account, not
    decisions the account holder makes. Email is excluded because changing it
    changes the sign-in identity and must go through verification.
    """

    class Meta:
        model = User
        fields = ["first_name", "last_name", "phone"]


class ShopperLocationSerializer(serializers.ModelSerializer):
    """
    What a shopper shares, and what they get back.

    `label` is read-only and derived server-side from the coordinates rather than accepted
    from the client, because it is what the product later shows the person as "we think you
    are near X". A client-supplied label could disagree with the coordinates it arrived with,
    and the shopper would have no way to tell which of the two the ranking actually used.
    """

    class Meta:
        model = ShopperLocation
        fields = ["latitude", "longitude", "accuracy_metres", "source", "label", "updated_at"]
        read_only_fields = ["label", "updated_at"]


class NotificationPreferencesSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreferences
        fields = [
            "order_updates",
            "delivery_updates",
            "prescription_reminders",
            "refill_reminders",
            "product_news",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]

