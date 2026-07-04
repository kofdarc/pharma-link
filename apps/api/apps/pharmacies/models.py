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

    class Meta:
        indexes = [models.Index(fields=["city", "area"])]
        constraints = [
            models.UniqueConstraint(fields=["name", "area"], name="unique_pharmacy_name_per_area"),
        ]

    def __str__(self) -> str:
        return f"{self.name} - {self.area}"

