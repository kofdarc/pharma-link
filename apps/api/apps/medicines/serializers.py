from django.utils import timezone
from rest_framework import serializers

from apps.medicines.models import Medicine, MedicineAlias, PriceRegime


class MedicineAliasSerializer(serializers.ModelSerializer):
    class Meta:
        model = MedicineAlias
        fields = ["id", "alias", "alias_type", "created_at"]
        read_only_fields = ["id", "created_at"]


class MedicineSerializer(serializers.ModelSerializer):
    aliases = MedicineAliasSerializer(many=True, required=False)
    display_name = serializers.SerializerMethodField()
    is_price_regulated = serializers.BooleanField(read_only=True)

    class Meta:
        model = Medicine
        fields = [
            "id",
            "brand_name",
            "generic_name",
            "strength",
            "form",
            "manufacturer",
            "classification",
            "notes",
            "image",
            "is_active",
            "category",
            "price_regime",
            "regulated_price",
            "regulated_price_reference",
            "regulated_price_updated_at",
            "requires_prescription",
            "drug_schedule",
            "is_price_regulated",
            "aliases",
            "display_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "display_name", "is_price_regulated", "regulated_price_updated_at"]

    def get_display_name(self, obj) -> str:
        return str(obj)

    def validate(self, attrs):
        regime = attrs.get("price_regime", getattr(self.instance, "price_regime", PriceRegime.REGULATED))
        price = attrs.get("regulated_price", getattr(self.instance, "regulated_price", None))
        if regime == PriceRegime.REGULATED and price is None:
            raise serializers.ValidationError({"regulated_price": "A MoPH regulated product must carry its published price."})
        if regime == PriceRegime.FREE:
            attrs["regulated_price"] = None
        return attrs

    def create(self, validated_data):
        aliases = validated_data.pop("aliases", [])
        if validated_data.get("regulated_price") is not None:
            validated_data["regulated_price_updated_at"] = timezone.now()
        medicine = Medicine.objects.create(**validated_data)
        for alias in aliases:
            MedicineAlias.objects.create(medicine=medicine, **alias)
        return medicine

    def update(self, instance, validated_data):
        aliases = validated_data.pop("aliases", None)
        if "regulated_price" in validated_data and validated_data["regulated_price"] != instance.regulated_price:
            validated_data["regulated_price_updated_at"] = timezone.now()
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.save()
        if aliases is not None:
            instance.aliases.all().delete()
            for alias in aliases:
                MedicineAlias.objects.create(medicine=instance, **alias)
        return instance

