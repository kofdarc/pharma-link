from datetime import time

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.common.models import UUIDTimeStampedModel


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

