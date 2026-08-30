"""
Public availability search: "I want paracetamol, I don't care whose shelf it's on."

Two rules shape this:
  1. Never expose a pharmacy's true stock depth. Results carry a capped, coarse figure
     (`available_up_to`) plus a status band - enough to decide, useless as competitor
     intelligence.
  2. Rank by what the shopper actually cares about: how close it is, how well the pharmacy
     has served people before, how reliably it fulfils, and price on free-priced lines
     (regulated lines are identical everywhere by law, so price is not a differentiator there).

Searches that find nothing are recorded as unmet demand, which is how pharmacies later see
the demand their own till could never show them.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db.models import Min, Q, Sum
from django.utils import timezone

from apps.common.geo import road_km
from apps.inventory.models import InventoryBatch
from apps.medicines.models import MarketStatus, Medicine
from apps.medicines.services.search import search_medicines

DISCLAIMER = (
    "Availability information is provided by connected pharmacies and may change. "
    "Please confirm with the pharmacy before visiting or using any medication."
)

# Ranking weights. Distance dominates, then reputation, then price on free-priced items.
DISTANCE_WEIGHT = 1.0
RATING_WEIGHT = 2.5
RELIABILITY_WEIGHT = 0.05
PRICE_WEIGHT = 0.4
UNRATED_RATING = 3.8


def availability_status(total_quantity: int, low_threshold: int) -> str:
    if total_quantity <= 0:
        return "Unavailable"
    if total_quantity <= low_threshold:
        return "Low stock"
    return "Available"


def public_cap(pharmacy_cap) -> int:
    return pharmacy_cap or settings.PUBLIC_MAX_QUANTITY_PER_ITEM


def _moph_extra(medicine: Medicine | None, key: str) -> str:
    """A handful of MoPH source fields (presentation/country/agent/brand-generic) live in
    the catch-all `moph_extra` JSON blob rather than dedicated columns - see Medicine.moph_extra."""
    if not medicine:
        return ""
    return medicine.moph_extra.get(key) or ""


def public_availability_search(
    *,
    query: str = "",
    area: str = "",
    medicine_id: str | None = None,
    same_composition_as: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    sort: str = "best",
    request=None,
):
    today = timezone.localdate()
    if medicine_id:
        medicines = Medicine.objects.filter(id=medicine_id, is_active=True)
    elif same_composition_as:
        # Candidate generation for "same composition" recommendations: the full
        # `ingredients` string already encodes strength (e.g. "Atorvastatin (calcium) -
        # 10mg"), so an exact match on it is a reasonable proxy for the same complete
        # active-ingredient set + strength - the strongest deterministic key available
        # without a structured per-ingredient/strength model (WHO pharmaceutical-equivalence
        # principles; Lebanon's MoPH substitution framework matches on the same basis).
        # Restricted to MARKETED products: a NON_MARKETED match cannot lawfully be sold.
        reference = Medicine.objects.filter(id=same_composition_as, is_active=True).first()
        if reference and reference.ingredients:
            medicines = Medicine.objects.filter(
                ingredients__iexact=reference.ingredients,
                is_active=True,
                market_status=MarketStatus.MARKETED,
            ).exclude(id=reference.id)
            if reference.route:
                # A tablet and an injection can share an ingredients string at the same
                # strength while being clinically nothing alike. Exclude a *known*
                # differing route; a candidate with no recorded route isn't excluded,
                # since missing data isn't evidence of a mismatch.
                medicines = medicines.filter(Q(route="") | Q(route__iexact=reference.route))
        else:
            medicines = Medicine.objects.none()
    else:
        medicines = search_medicines(query, active_only=True, limit=20)

    medicine_ids = [medicine.id for medicine in medicines]
    if not medicine_ids:
        _record_unmet(query=query, area=area)
        return []

    medicine_map = {item.id: item for item in Medicine.objects.filter(id__in=medicine_ids)}

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
            "pharmacy_id",
            "pharmacy__name",
            "pharmacy__address",
            "pharmacy__city",
            "pharmacy__area",
            "pharmacy__phone",
            "pharmacy__whatsapp",
            "pharmacy__email",
            "pharmacy__latitude",
            "pharmacy__longitude",
            "pharmacy__rating_average",
            "pharmacy__rating_count",
            "pharmacy__fulfillment_success_rate",
            "pharmacy__is_on_call",
            "pharmacy__accepts_online_orders",
            "pharmacy__delivery_enabled",
            "pharmacy__public_max_quantity_per_item",
            "pharmacy__order_preparation_minutes",
        )
        .annotate(
            total_quantity=Sum("current_quantity"),
            held_quantity=Sum("reserved_quantity"),
            low_threshold=Min("low_stock_threshold"),
            best_price=Min("selling_price"),
            soonest_expiry=Min("expiry_date"),
        )
        .order_by("medicine__brand_name", "pharmacy__name")
    )

    results = []
    for row in grouped:
        medicine = medicine_map.get(row["medicine_id"])
        sellable = max(0, (row["total_quantity"] or 0) - (row["held_quantity"] or 0))
        if sellable <= 0:
            continue
        cap = public_cap(row["pharmacy__public_max_quantity_per_item"])
        capped = min(sellable, cap)
        threshold = max(1, row["low_threshold"] or 1)

        distance = None
        if latitude is not None and longitude is not None and row["pharmacy__latitude"] is not None:
            distance = round(road_km(latitude, longitude, float(row["pharmacy__latitude"]), float(row["pharmacy__longitude"])), 2)

        rating = float(row["pharmacy__rating_average"]) if row["pharmacy__rating_count"] else UNRATED_RATING
        unit_price = row["best_price"]
        is_regulated = bool(medicine and medicine.is_price_regulated)
        if is_regulated:
            unit_price = medicine.regulated_price

        latest_batch = qs.filter(medicine_id=row["medicine_id"], pharmacy_id=row["pharmacy_id"]).order_by("-updated_at").first()
        image_url = None
        if medicine and medicine.image:
            image_url = request.build_absolute_uri(medicine.image.url) if request else medicine.image.url
        results.append(
            {
                "medicine": {
                    "id": row["medicine_id"],
                    "brand_name": medicine.brand_name if medicine else "",
                    "generic_name": medicine.generic_name if medicine else "",
                    "strength": medicine.strength if medicine else "",
                    "form": medicine.form if medicine else "",
                    "route": medicine.route if medicine else "",
                    "category": medicine.category if medicine else "",
                    "requires_prescription": bool(medicine and medicine.requires_prescription),
                    "image": image_url,
                    # Composition/manufacturer/registration fields are exposed alongside,
                    # never instead of, structured ingredient matching - "brand/generic" and
                    # "manufacturer" are transparency fields, not an equivalence signal.
                    "manufacturer": medicine.manufacturer if medicine else "",
                    "ingredients": medicine.ingredients if medicine else "",
                    "classification": medicine.classification if medicine else "",
                    "registration_number": medicine.registration_number if medicine else "",
                    "presentation": _moph_extra(medicine, "presentation"),
                    "country": _moph_extra(medicine, "country"),
                    "agent": _moph_extra(medicine, "agent"),
                    "brand_generic": _moph_extra(medicine, "brand_generic"),
                    "market_status": medicine.market_status if medicine else "",
                    # NSSF reimbursement, so a shopper sees whether the Fund covers it and
                    # roughly what they would still pay. Reference price/rate are null when
                    # the medicine is covered but that detail is not yet on file.
                    "nssf_covered": bool(medicine and medicine.nssf_covered),
                    "nssf_reference_price": (
                        str(medicine.nssf_reference_price)
                        if medicine and medicine.nssf_reference_price is not None
                        else None
                    ),
                    "nssf_reimbursement_rate": (
                        str(medicine.nssf_reimbursement_rate)
                        if medicine and medicine.nssf_reimbursement_rate is not None
                        else None
                    ),
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
                    "rating": round(rating, 2),
                    "rating_count": row["pharmacy__rating_count"],
                    "fulfillment_success_rate": float(row["pharmacy__fulfillment_success_rate"]),
                    "is_on_call": row["pharmacy__is_on_call"],
                    "accepts_online_orders": row["pharmacy__accepts_online_orders"],
                    "delivery_enabled": row["pharmacy__delivery_enabled"],
                    "preparation_minutes": row["pharmacy__order_preparation_minutes"],
                },
                "availability_status": availability_status(sellable, threshold),
                # Capped on purpose: shoppers learn what they can get, not what the pharmacy holds.
                "available_up_to": capped,
                "quantity_cap": cap,
                "unit_price": unit_price,
                "is_price_regulated": is_regulated,
                "price_note": "Price set by the Ministry of Public Health" if is_regulated else "Price set by the pharmacy",
                "distance_km": distance,
                "soonest_expiry": row["soonest_expiry"],
                "last_updated": latest_batch.updated_at if latest_batch else None,
                "rank_score": _rank_score(distance=distance, rating=rating, reliability=float(row["pharmacy__fulfillment_success_rate"]), price=unit_price, is_regulated=is_regulated),
                "disclaimer": DISCLAIMER,
            }
        )

    if not results:
        _record_unmet(query=query, area=area, medicine_id=medicine_ids[0] if len(medicine_ids) == 1 else None)
        return []

    if sort == "distance" and latitude is not None:
        results.sort(key=lambda row: (row["distance_km"] is None, row["distance_km"] or 0))
    elif sort == "price":
        results.sort(key=lambda row: (row["unit_price"] is None, row["unit_price"] or 0))
    elif sort == "rating":
        results.sort(key=lambda row: -row["pharmacy"]["rating"])
    else:
        results.sort(key=lambda row: row["rank_score"])
    return results


def _rank_score(*, distance, rating: float, reliability: float, price, is_regulated: bool) -> float:
    """Lower is better. Distance in km is the base unit; everything else is expressed against it."""
    score = DISTANCE_WEIGHT * (distance if distance is not None else 5.0)
    score += RATING_WEIGHT * (5.0 - rating)
    score += RELIABILITY_WEIGHT * (100.0 - reliability)
    if not is_regulated and price is not None:
        score += PRICE_WEIGHT * float(Decimal(str(price)))
    return round(score, 4)


def _record_unmet(*, query: str, area: str, medicine_id=None) -> None:
    from apps.orders.models import UnmetDemandSignal

    if not query and not medicine_id:
        return
    UnmetDemandSignal.objects.create(
        medicine_id=medicine_id,
        query_text=(query or "")[:255],
        area=(area or "")[:120],
        source=UnmetDemandSignal.Source.SEARCH,
    )
