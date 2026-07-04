from __future__ import annotations

from django.db.models import Sum
from django.utils import timezone

from apps.inventory.models import InventoryBatch
from apps.medicines.models import Medicine
from apps.medicines.services.search import search_medicines


def availability_status(total_quantity: int, low_threshold: int) -> str:
    if total_quantity <= 0:
        return "Unavailable"
    if total_quantity <= low_threshold:
        return "Low stock"
    return "Available"


def public_availability_search(*, query: str = "", area: str = "", medicine_id: str | None = None):
    today = timezone.localdate()
    if medicine_id:
        medicines = Medicine.objects.filter(id=medicine_id, is_active=True)
    else:
        medicines = search_medicines(query, active_only=True, limit=20)

    medicine_ids = [medicine.id for medicine in medicines]
    if not medicine_ids:
        return []

    qs = (
        InventoryBatch.objects.select_related("pharmacy", "medicine")
        .filter(
            medicine_id__in=medicine_ids,
            pharmacy__is_active=True,
            pharmacy__is_public=True,
            medicine__is_active=True,
            public_availability_enabled=True,
            is_archived=False,
            current_quantity__gt=0,
        )
        .exclude(expiry_date__lt=today)
    )
    if area:
        qs = qs.filter(pharmacy__area__icontains=area)

    grouped = (
        qs.values(
            "medicine_id",
            "medicine__brand_name",
            "medicine__generic_name",
            "medicine__strength",
            "medicine__form",
            "pharmacy_id",
            "pharmacy__name",
            "pharmacy__address",
            "pharmacy__city",
            "pharmacy__area",
            "pharmacy__phone",
            "pharmacy__whatsapp",
            "pharmacy__email",
        )
        .annotate(total_quantity=Sum("current_quantity"), low_threshold=Sum("low_stock_threshold"))
        .order_by("medicine__brand_name", "pharmacy__area", "pharmacy__name")
    )

    results = []
    for row in grouped:
        total = row.pop("total_quantity") or 0
        threshold = max(1, row.pop("low_threshold") or 1)
        latest_batch = qs.filter(medicine_id=row["medicine_id"], pharmacy_id=row["pharmacy_id"]).order_by("-updated_at").first()
        results.append(
            {
                "medicine": {
                    "id": row["medicine_id"],
                    "brand_name": row["medicine__brand_name"],
                    "generic_name": row["medicine__generic_name"],
                    "strength": row["medicine__strength"],
                    "form": row["medicine__form"],
                },
                "pharmacy": {
                    "id": row["pharmacy_id"],
                    "name": row["pharmacy__name"],
                    "address": row["pharmacy__address"],
                    "city": row["pharmacy__city"],
                    "area": row["pharmacy__area"],
                    "phone": row["pharmacy__phone"],
                    "whatsapp": row["pharmacy__whatsapp"],
                    "email": row["pharmacy__email"],
                },
                "availability_status": availability_status(total, threshold),
                "last_updated": latest_batch.updated_at if latest_batch else None,
                "disclaimer": "Availability information is provided by connected pharmacies and may change. Please confirm with the pharmacy before visiting or using any medication.",
            }
        )
    return results

