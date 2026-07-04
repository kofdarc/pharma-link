from rest_framework import serializers

from apps.medicines.models import Medicine, MedicineAlias


class MedicineAliasSerializer(serializers.ModelSerializer):
    class Meta:
        model = MedicineAlias
        fields = ["id", "alias", "alias_type", "created_at"]
        read_only_fields = ["id", "created_at"]


class MedicineSerializer(serializers.ModelSerializer):
    aliases = MedicineAliasSerializer(many=True, required=False)
    display_name = serializers.SerializerMethodField()

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
            "is_active",
            "aliases",
            "display_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "display_name"]

    def get_display_name(self, obj) -> str:
        return str(obj)

    def create(self, validated_data):
        aliases = validated_data.pop("aliases", [])
        medicine = Medicine.objects.create(**validated_data)
        for alias in aliases:
            MedicineAlias.objects.create(medicine=medicine, **alias)
        return medicine

    def update(self, instance, validated_data):
        aliases = validated_data.pop("aliases", None)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.save()
        if aliases is not None:
            instance.aliases.all().delete()
            for alias in aliases:
                MedicineAlias.objects.create(medicine=instance, **alias)
        return instance

