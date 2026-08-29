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
    # A handful of MoPH source fields (pack presentation/country/local agent/brand-generic
    # classification) live in the catch-all `moph_extra` JSON blob rather than dedicated
    # columns - see Medicine.moph_extra. Only the fields worth showing to a shopper are
    # pulled out here; things like pharmacist_margin/stratum/price_ll/exch_date stay buried,
    # deliberately, because they're MoPH trade/pricing bookkeeping, not product information.
    presentation = serializers.SerializerMethodField()
    country = serializers.SerializerMethodField()
    agent = serializers.SerializerMethodField()
    brand_generic = serializers.SerializerMethodField()

    class Meta:
        model = Medicine
        fields = [
            "id",
            "brand_name",
            "generic_name",
            "strength",
            "form",
            "route",
            "manufacturer",
            "classification",
            "ingredients",
            "registration_number",
            "market_status",
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
            "presentation",
            "country",
            "agent",
            "brand_generic",
            "aliases",
            "display_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "display_name", "is_price_regulated", "regulated_price_updated_at"]

    def get_display_name(self, obj) -> str:
        return str(obj)

    def _moph_extra(self, obj, key: str) -> str:
        return (obj.moph_extra or {}).get(key) or ""

    def get_presentation(self, obj) -> str:
        return self._moph_extra(obj, "presentation")

    def get_country(self, obj) -> str:
        return self._moph_extra(obj, "country")

    def get_agent(self, obj) -> str:
        return self._moph_extra(obj, "agent")

    def get_brand_generic(self, obj) -> str:
        return self._moph_extra(obj, "brand_generic")

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

