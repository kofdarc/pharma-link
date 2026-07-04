from django.db import models
from django.db.models.functions import Lower

from apps.common.models import UUIDTimeStampedModel


class Medicine(UUIDTimeStampedModel):
    brand_name = models.CharField(max_length=255, db_index=True)
    generic_name = models.CharField(max_length=255, blank=True, db_index=True)
    strength = models.CharField(max_length=80, blank=True)
    form = models.CharField(max_length=80, blank=True)
    manufacturer = models.CharField(max_length=160, blank=True)
    classification = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("brand_name"),
                Lower("strength"),
                Lower("form"),
                condition=models.Q(is_active=True),
                name="unique_active_medicine_variant",
            )
        ]

    def __str__(self) -> str:
        variant = " ".join(part for part in [self.brand_name, self.strength, self.form] if part)
        return variant or self.brand_name


class MedicineAlias(UUIDTimeStampedModel):
    class AliasType(models.TextChoices):
        BRAND_VARIATION = "BRAND_VARIATION", "Brand variation"
        GENERIC = "GENERIC", "Generic"
        MISSPELLING = "MISSPELLING", "Misspelling"
        IMPORT_NAME = "IMPORT_NAME", "Import name"
        OTHER = "OTHER", "Other"

    medicine = models.ForeignKey(Medicine, on_delete=models.CASCADE, related_name="aliases")
    alias = models.CharField(max_length=255, db_index=True)
    alias_type = models.CharField(max_length=32, choices=AliasType.choices, default=AliasType.OTHER)

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("alias"), "medicine", name="unique_alias_per_medicine"),
        ]

    def __str__(self) -> str:
        return self.alias

