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
    # Percentage of the NSSF reference price the patient still pays; null when the
    # medicine is covered but no rate is on file yet. Derived, never written.
    nssf_patient_share_percentage = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)

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
            "nssf_covered",
            "nssf_reference_price",
            "nssf_reimbursement_rate",
            "nssf_source_reference",
            "nssf_updated_at",
            "nssf_patient_share_percentage",
            "presentation",
            "country",
            "agent",
            "brand_generic",
            "aliases",
            "display_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "display_name",
            "is_price_regulated",
            "regulated_price_updated_at",
            "nssf_updated_at",
            "nssf_patient_share_percentage",
        ]

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

        covered = attrs.get("nssf_covered", getattr(self.instance, "nssf_covered", False))
        if not covered:
            # A medicine that is not on an NSSF list carries no reference price or rate;
            # null them rather than rejecting, so unchecking the box just works.
            if "nssf_covered" in attrs or self.instance is None:
                attrs["nssf_reference_price"] = None
                attrs["nssf_reimbursement_rate"] = None
        return attrs

    _NSSF_FIELDS = ("nssf_covered", "nssf_reference_price", "nssf_reimbursement_rate", "nssf_source_reference")

    def create(self, validated_data):
        aliases = validated_data.pop("aliases", [])
        if validated_data.get("regulated_price") is not None:
            validated_data["regulated_price_updated_at"] = timezone.now()
        if any(field in validated_data for field in self._NSSF_FIELDS):
            validated_data["nssf_updated_at"] = timezone.now()
        medicine = Medicine.objects.create(**validated_data)
        for alias in aliases:
            MedicineAlias.objects.create(medicine=medicine, **alias)
        return medicine

    def update(self, instance, validated_data):
        aliases = validated_data.pop("aliases", None)
        if "regulated_price" in validated_data and validated_data["regulated_price"] != instance.regulated_price:
            validated_data["regulated_price_updated_at"] = timezone.now()
        if any(field in validated_data and validated_data[field] != getattr(instance, field) for field in self._NSSF_FIELDS):
            validated_data["nssf_updated_at"] = timezone.now()
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.save()
        if aliases is not None:
            instance.aliases.all().delete()
            for alias in aliases:
                MedicineAlias.objects.create(medicine=instance, **alias)
        return instance

