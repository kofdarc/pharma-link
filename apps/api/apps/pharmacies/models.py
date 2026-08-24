from datetime import time

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.common.models import UUIDTimeStampedModel


class PosSystem(models.TextChoices):
    NONE = "NONE", "No POS system (dashboard/manual only)"
    SOFTPHARM = "SOFTPHARM", "SoftPharm (NIT)"
    OTHER = "OTHER", "Other"


class Pharmacy(UUIDTimeStampedModel):
    name = models.CharField(max_length=255)
    license_number = models.CharField(max_length=80, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=120, db_index=True)
    area = models.CharField(max_length=120, db_index=True)
    phone = models.CharField(max_length=40)
    whatsapp = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True, validators=[MinValueValidator(-90), MaxValueValidator(90)])
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True, validators=[MinValueValidator(-180), MaxValueValidator(180)])
    is_active = models.BooleanField(default=True)
    is_public = models.BooleanField(default=True)
    is_on_call = models.BooleanField(
        default=False, db_index=True, help_text="Currently on Lebanon's pharmacy duty roster ('de garde') - reachable outside normal hours."
    )
    pos_system = models.CharField(
        max_length=20,
        choices=PosSystem.choices,
        default=PosSystem.NONE,
        blank=True,
        db_index=True,
        help_text="Which POS/pharmacy-management software this pharmacy runs, if any - drives which connector template applies.",
    )

    # Consumer-facing controls. Pharmacies never expose their true stock depth publicly:
    # shoppers see and can order at most this many units of an item at a time.
    accepts_online_orders = models.BooleanField(default=True)
    public_max_quantity_per_item = models.PositiveIntegerField(null=True, blank=True, help_text="Overrides the platform default cap on publicly visible/orderable units.")
    delivery_enabled = models.BooleanField(default=True)
    order_preparation_minutes = models.PositiveIntegerField(default=15)
    opens_at = models.TimeField(default=time(8, 0))
    closes_at = models.TimeField(default=time(21, 0))

    # Rolling service reputation, refreshed from completed orders and shopper reviews.
    rating_average = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    rating_count = models.PositiveIntegerField(default=0)
    fulfillment_success_rate = models.DecimalField(max_digits=5, decimal_places=2, default=100, help_text="Percent of accepted orders handed over without a shortfall.")
    orders_fulfilled = models.PositiveIntegerField(default=0)
    orders_rejected = models.PositiveIntegerField(default=0)

    class Meta:
        indexes = [models.Index(fields=["city", "area"])]
        constraints = [
            models.UniqueConstraint(fields=["name", "area"], name="unique_pharmacy_name_per_area"),
        ]

    def __str__(self) -> str:
        return f"{self.name} - {self.area}"


class PharmacyApplication(UUIDTimeStampedModel):
    """
    A prospective pharmacy's in-product request to join, since Pharmacy records are
    otherwise only ever created by a platform admin (apps.pharmacies.views.AdminPharmacyViewSet).
    Approving one creates the real Pharmacy + owner User via apps.pharmacies.services.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending review"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    pharmacy_name = models.CharField(max_length=255)
    owner_name = models.CharField(max_length=255)
    email = models.EmailField()
    phone = models.CharField(max_length=40)
    city = models.CharField(max_length=120, blank=True)
    area = models.CharField(max_length=120, blank=True)
    license_number = models.CharField(max_length=80, blank=True)
    message = models.TextField(blank=True, help_text="Anything else the applicant wants reviewers to know.")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    review_note = models.CharField(max_length=255, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_pharmacy = models.ForeignKey(Pharmacy, null=True, blank=True, on_delete=models.SET_NULL, related_name="application")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.pharmacy_name} ({self.status})"

