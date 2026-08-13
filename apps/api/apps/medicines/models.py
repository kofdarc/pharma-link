from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models.functions import Lower

from apps.common.models import UUIDTimeStampedModel


class ProductCategory(models.TextChoices):
    """Regulated medicines are priced by the Ministry of Public Health; the rest are free-priced."""

    MEDICINE = "MEDICINE", "Medicine (MoPH regulated price)"
    SUPPLEMENT = "SUPPLEMENT", "Supplement"
    PARAPHARMACY = "PARAPHARMACY", "Parapharmacy / other"


class PriceRegime(models.TextChoices):
    REGULATED = "REGULATED", "MoPH regulated"
    FREE = "FREE", "Free pricing"


class Medicine(UUIDTimeStampedModel):
    brand_name = models.CharField(max_length=255, db_index=True)
    generic_name = models.CharField(max_length=255, blank=True, db_index=True)
    strength = models.CharField(max_length=80, blank=True)
    form = models.CharField(max_length=80, blank=True)
    manufacturer = models.CharField(max_length=160, blank=True)
    classification = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    category = models.CharField(max_length=20, choices=ProductCategory.choices, default=ProductCategory.MEDICINE, db_index=True)
    price_regime = models.CharField(max_length=20, choices=PriceRegime.choices, default=PriceRegime.REGULATED, db_index=True)
    regulated_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Public price set by the Ministry of Public Health. Required when price_regime is REGULATED.",
    )
    regulated_price_reference = models.CharField(max_length=120, blank=True, help_text="MoPH price list / decision reference.")
    regulated_price_updated_at = models.DateTimeField(null=True, blank=True)
    requires_prescription = models.BooleanField(default=False)

    @property
    def is_price_regulated(self) -> bool:
        return self.price_regime == PriceRegime.REGULATED and self.regulated_price is not None

    def clean(self):
        if self.price_regime == PriceRegime.REGULATED and self.regulated_price is None:
            raise ValidationError({"regulated_price": "A MoPH regulated product must carry its published price."})

    def validate_selling_price(self, selling_price) -> None:
        """MoPH prices are not a ceiling, they are the price. Free-priced products are left to the pharmacy."""
        if not self.is_price_regulated or selling_price is None:
            return
        if Decimal(str(selling_price)) != self.regulated_price:
            raise ValidationError(
                {
                    "selling_price": (
                        f"{self} is priced by the Ministry of Public Health at {self.regulated_price}. "
                        "Regulated products must be sold at the published price."
                    )
                }
            )

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

