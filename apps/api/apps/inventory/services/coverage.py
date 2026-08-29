"""
"Which single pharmacy near me has ALL of this?" - the whole-basket version of availability.

`availability.public_availability_search` answers a question about one medicine at a time,
which is the wrong shape for the question people actually ask about a prescription: three
lines on a script, and what they want to know is whether one trip covers it. Answering that
by running the single-medicine search three times and intersecting the results by hand is
what every caller would otherwise do, and each of them would get the caps, the reservation
maths and the expiry filter slightly differently.

This is a read, not a plan. `apps.orders.services.sourcing` already decides which pharmacies
should *fill* a basket, splitting it across several when that is better and holding stock
while it does - that is the checkout path and it has consequences. This module holds nothing
and commits to nothing: it reports what each pharmacy near a point could currently cover, so
the shopper (or the assistant answering them) can decide. Same caps, same expiry rule, same
reserved-unit arithmetic as the public search, because a pharmacy that "has all three" here
and shows two on the search page would be a bug people notice immediately.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db.models import Min, Sum
from django.utils import timezone

from apps.common.geo import road_km
from apps.inventory.models import InventoryBatch
from apps.medicines.models import Medicine
from apps.pharmacies.models import Pharmacy

MAX_ROWS = 5
UNRATED_RATING = 3.8


def pharmacies_covering(
    *,
    needs: dict[str, int],
    latitude: float | None = None,
    longitude: float | None = None,
    radius_km: float | None = None,
    limit: int = MAX_ROWS,
) -> list[dict]:
    """
    needs: {medicine_id: units wanted}. Units default to 1 where a caller only knows the
    medicine (a prescription line whose quantity is already partly dispensed, say).

    Returns one row per pharmacy that can cover at least one line, best first: full coverage
    ahead of partial, then nearest, then best rated. Pharmacies with no coordinates on file
    are included but rank last - they are still a real answer to "who has this", just not to
    "which is nearest".

    `radius_km` only applies when a position is known; without one there is nothing to
    measure a radius against and every connected pharmacy is a candidate.
    """
    wanted = {str(key): max(1, int(units)) for key, units in (needs or {}).items()}
    if not wanted:
        return []

    medicines = {str(item.id): item for item in Medicine.objects.filter(id__in=list(wanted), is_active=True)}
    if not medicines:
        return []

    today = timezone.localdate()
    rows = (
        InventoryBatch.objects.filter(
            medicine_id__in=list(medicines),
            pharmacy__is_active=True,
            pharmacy__is_public=True,
            medicine__is_active=True,
            public_availability_enabled=True,
            is_archived=False,
            current_quantity__gt=0,
        )
        .exclude(expiry_date__lt=today)
        .values("pharmacy_id", "medicine_id")
        .annotate(units=Sum("current_quantity"), held=Sum("reserved_quantity"), best_price=Min("selling_price"))
    )

    pharmacy_ids = {row["pharmacy_id"] for row in rows}
    if not pharmacy_ids:
        return []
    pharmacies = {item.id: item for item in Pharmacy.objects.filter(id__in=pharmacy_ids)}
    has_origin = latitude is not None and longitude is not None
    reach_km = radius_km or settings.MAX_SOURCING_RADIUS_KM

    holdings: dict = {}
    for row in rows:
        pharmacy = pharmacies[row["pharmacy_id"]]
        distance = None
        if has_origin and pharmacy.latitude is not None and pharmacy.longitude is not None:
            distance = round(road_km(latitude, longitude, float(pharmacy.latitude), float(pharmacy.longitude)), 2)
            if distance > reach_km:
                continue

        medicine_id = str(row["medicine_id"])
        medicine = medicines[medicine_id]
        sellable = max(0, (row["units"] or 0) - (row["held"] or 0))
        # Same cap as everywhere else: what the shopper could order, never what is on the shelf.
        offered = min(sellable, pharmacy.public_max_quantity_per_item or settings.PUBLIC_MAX_QUANTITY_PER_ITEM)
        if offered <= 0:
            continue

        entry = holdings.setdefault(pharmacy.id, {"pharmacy": pharmacy, "distance_km": distance, "lines": []})
        entry["lines"].append(
            {
                "medicine_id": medicine_id,
                "medicine": medicine.brand_name,
                "strength": medicine.strength,
                "requires_prescription": medicine.requires_prescription,
                "requested": wanted[medicine_id],
                "available_up_to": offered,
                "covers_requested": offered >= wanted[medicine_id],
                "unit_price": str(medicine.regulated_price if medicine.is_price_regulated else row["best_price"]),
                "is_price_regulated": medicine.is_price_regulated,
            }
        )

    results = [_row(entry, wanted, medicines) for entry in holdings.values()]
    # Full coverage first; then nearest, with unlocatable pharmacies last rather than first
    # (a None distance must not sort as zero); then the better-regarded pharmacy.
    results.sort(key=lambda row: (not row["covers_everything"], row["distance_km"] is None, row["distance_km"] or 0, -row["rating"]))
    return results[:limit]


def _row(entry: dict, wanted: dict[str, int], medicines: dict) -> dict:
    pharmacy = entry["pharmacy"]
    lines = entry["lines"]
    covered_ids = {line["medicine_id"] for line in lines if line["covers_requested"]}
    missing = [
        {"medicine": medicines[medicine_id].brand_name, "requested": units, "reason": "short" if medicine_id in {line["medicine_id"] for line in lines} else "none"}
        for medicine_id, units in wanted.items()
        if medicine_id not in covered_ids
    ]
    return {
        "pharmacy": {
            "id": str(pharmacy.id),
            "name": pharmacy.name,
            "area": pharmacy.area,
            "city": pharmacy.city,
            "address": pharmacy.address,
            "phone": pharmacy.phone,
            "is_on_call": pharmacy.is_on_call,
            "delivery_enabled": pharmacy.delivery_enabled,
            "accepts_online_orders": pharmacy.accepts_online_orders,
            "opens_at": pharmacy.opens_at.strftime("%H:%M"),
            "closes_at": pharmacy.closes_at.strftime("%H:%M"),
        },
        "distance_km": entry["distance_km"],
        "rating": round(float(pharmacy.rating_average) if pharmacy.rating_count else UNRATED_RATING, 2),
        "lines": lines,
        "missing": missing,
        "covers_everything": not missing,
        "lines_covered": len(covered_ids),
        "lines_requested": len(wanted),
        "requires_prescription": [line["medicine"] for line in lines if line["requires_prescription"]],
        "basket_total": str(sum((Decimal(line["unit_price"]) * min(line["available_up_to"], line["requested"]) for line in lines), Decimal("0"))),
    }
