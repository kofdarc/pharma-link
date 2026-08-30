from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.functions import Lower

from apps.common.models import UUIDTimeStampedModel
from apps.medicines.storage import ProductImageStorage


def medicine_image_path(instance, filename):
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    suffix = f".{extension}" if extension else ""
    return f"medicines/{instance.pk}{suffix}"


class ProductCategory(models.TextChoices):
    """Regulated medicines are priced by the Ministry of Public Health; the rest are free-priced."""

    MEDICINE = "MEDICINE", "Medicine (MoPH regulated price)"
    SUPPLEMENT = "SUPPLEMENT", "Supplement"
    PARAPHARMACY = "PARAPHARMACY", "Parapharmacy / other"


class PriceRegime(models.TextChoices):
    REGULATED = "REGULATED", "MoPH regulated"
    FREE = "FREE", "Free pricing"


class MarketStatus(models.TextChoices):
    """Whether MoPH currently lists the product as commercially marketed in Lebanon.

    This is independent of pharmacy stock/inventory - a MARKETED product may still
    be out of stock everywhere, and that must never be inferred as NON_MARKETED.
    """

    MARKETED = "MARKETED", "Marketed"
    NON_MARKETED = "NON_MARKETED", "Registered, not currently marketed"


class MophSource(models.TextChoices):
    """Which MoPH source last supplied/confirmed a product's authoritative data."""

    MOPH_ONLINE = "MOPH_ONLINE", "MoPH Lebanon National Drugs Database (online)"
    MOPH_MARKETED_EXCEL = "MOPH_MARKETED_EXCEL", "MoPH WebMarketed price list (Excel)"
    MOPH_NON_MARKETED_EXCEL = "MOPH_NON_MARKETED_EXCEL", "MoPH WebNonMarketed price list (Excel)"


class DrugSchedule(models.TextChoices):
    """
    Not sourced from an official Lebanese controlled-substance list - every medicine defaults
    to NONE. A platform admin classifies individual items as they're identified, and only
    CONTROLLED items get the stricter dispensing rules in eprescriptions/services/dispense.py
    and orders/services/schedule.py.
    """

    NONE = "NONE", "Not scheduled"
    PRESCRIPTION = "PRESCRIPTION", "Prescription required"
    CONTROLLED = "CONTROLLED", "Controlled substance"


class Medicine(UUIDTimeStampedModel):
    brand_name = models.CharField(max_length=255, db_index=True)
    generic_name = models.CharField(max_length=255, blank=True, db_index=True)
    strength = models.CharField(max_length=80, blank=True)
    form = models.CharField(max_length=80, blank=True)
    manufacturer = models.CharField(max_length=160, blank=True)
    classification = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    image = models.ImageField(
        upload_to=medicine_image_path, storage=ProductImageStorage(), blank=True, null=True, help_text="Product photo shown to shoppers."
    )
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
    drug_schedule = models.CharField(max_length=20, choices=DrugSchedule.choices, default=DrugSchedule.NONE, db_index=True)

    # --- MoPH catalog sync fields ---
    # `moph_code` is MoPH's own "Code" identifier: present, unique, and stable across
    # the online Lebanon National Drugs Database and both WebMarketed/WebNonMarketed
    # Excel files (verified against live data - never overlaps between the two Excel
    # files, so it safely survives a product moving between MARKETED and NON_MARKETED).
    # It is the canonical identity key for sync upserts; brand/strength/form text is
    # only used as a one-time fallback match for rows synced before this field existed.
    moph_code = models.PositiveIntegerField(null=True, blank=True, unique=True, db_index=True)
    market_status = models.CharField(max_length=20, choices=MarketStatus.choices, default=MarketStatus.MARKETED, db_index=True)
    registration_number = models.CharField(max_length=80, blank=True)
    # Active-ingredient composition string (e.g. "Paracetamol - 500mg"), deliberately
    # separate from `classification` (which holds the ATC code) - the two are queried
    # independently and must never be conflated.
    ingredients = models.TextField(blank=True)
    route = models.CharField(max_length=80, blank=True)
    moph_source = models.CharField(max_length=32, choices=MophSource.choices, blank=True)
    moph_source_reference = models.CharField(max_length=255, blank=True, help_text="MoPH source URL/file this record was last synced from.")
    moph_last_synced_at = models.DateTimeField(null=True, blank=True)
    # Lower-value/reference-only MoPH fields that nothing in this app queries on yet,
    # kept here instead of as dedicated columns. Keys used: presentation, agent,
    # laboratory, country, pharmacist_margin, stratum, responsible_party_name,
    # responsible_party_country, exch_date, subsidy_percent, brand_generic.
    moph_extra = models.JSONField(default=dict, blank=True)

    # --- NSSF (National Social Security Fund) reimbursement ---
    # The NSSF publishes its own formulary of reimbursable drugs (cnss.gov.lb), separate
    # from anything MoPH provides and unrelated to `moph_extra["subsidy_percent"]` (which
    # is the Banque du Liban import subsidy). A medicine is "covered" when it appears on
    # an NSSF list; the list also fixes a reference price (since 2024 the cheapest
    # equivalent formulation) and a reimbursement rate (commonly 80%, 90/95% for
    # registered chronic/incurable conditions). There is no shared NSSF API - these are
    # populated by a platform admin or a one-off import of the NSSF PDF lists.
    nssf_covered = models.BooleanField(default=False, db_index=True)
    nssf_reference_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="NSSF reference (reimbursement-ceiling) price in the same currency as regulated_price.",
    )
    nssf_reimbursement_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        help_text="Share of the reference price the NSSF reimburses, as a percentage (e.g. 80.00).",
    )
    nssf_source_reference = models.CharField(
        max_length=255, blank=True, help_text="Which NSSF list/decision (name + date) this coverage was taken from."
    )
    nssf_updated_at = models.DateTimeField(null=True, blank=True)

    @property
    def is_price_regulated(self) -> bool:
        return self.price_regime == PriceRegime.REGULATED and self.regulated_price is not None

    @property
    def nssf_patient_share_percentage(self) -> Decimal | None:
        """The percentage of the reference price the patient still pays out of pocket,
        or None when the reimbursement rate is unknown (covered but rate not on file)."""
        if not self.nssf_covered or self.nssf_reimbursement_rate is None:
            return None
        return Decimal("100") - self.nssf_reimbursement_rate

    @property
    def is_controlled(self) -> bool:
        return self.drug_schedule == DrugSchedule.CONTROLLED

    @property
    def is_marketed(self) -> bool:
        return self.market_status == MarketStatus.MARKETED

    def validate_can_be_sold(self) -> None:
        """MoPH's Non-Marketed registry means "registered, but not actively marketed
        for sale in pharmacies" - by that definition a NON_MARKETED product cannot be
        newly sold. This does not affect existing inventory/stock records, only new
        sale/order transactions - see create_sale.py and orders/services/placement.py."""
        if not self.is_marketed:
            raise ValidationError(
                {"medicine": f"{self} is registered with the Ministry of Public Health but not currently marketed in Lebanon, and cannot be sold."}
            )

    def clean(self):
        if self.price_regime == PriceRegime.REGULATED and self.regulated_price is None:
            raise ValidationError({"regulated_price": "A MoPH regulated product must carry its published price."})
        if not self.nssf_covered and (self.nssf_reference_price is not None or self.nssf_reimbursement_rate is not None):
            raise ValidationError(
                {"nssf_covered": "Clear the NSSF reference price and reimbursement rate for a medicine that is not NSSF covered."}
            )

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
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(is_active=False)
                    | models.Q(price_regime=PriceRegime.FREE)
                    | models.Q(regulated_price__isnull=False)
                ),
                name="active_regulated_medicine_has_price",
            ),
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
        TRANSLITERATION = "TRANSLITERATION", "Transliteration (e.g. Arabic script)"
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

