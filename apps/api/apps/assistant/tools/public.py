"""
Lookups any visitor may run, signed in or not.

Nothing here touches a personal record: it is the public catalogue and the public availability
view, the same data the unauthenticated /api/public/search/ endpoint already serves. That is
why these are the guest persona's entire toolset - there is nothing to leak.
"""

from __future__ import annotations

from apps.assistant.tools.base import ToolContext
from apps.common.geo import road_km
from apps.inventory.services.availability import public_availability_search
from apps.medicines.services.search import search_medicines
from apps.pharmacies.models import Pharmacy

MAX_ROWS = 5


def _medicine_summary(medicine) -> dict:
    return {
        "id": str(medicine.id),
        "brand_name": medicine.brand_name,
        "generic_name": medicine.generic_name,
        "strength": medicine.strength,
        "form": medicine.form,
        "requires_prescription": medicine.requires_prescription,
        "is_price_regulated": medicine.is_price_regulated,
    }


def search_availability(ctx: ToolContext) -> dict:
    """Which connected pharmacies currently have a medicine, nearest first when we know where."""
    query = ctx.text("query")
    if not query:
        return {"query": "", "results": []}

    latitude, longitude = ctx.coordinates

    # Reuses the ranked public search rather than querying InventoryBatch directly, so the
    # assistant is subject to exactly the same public quantity caps, price-regime handling and
    # unmet-demand recording as the search page. An answer here and an answer there can never
    # disagree, and a miss still feeds the unmet-demand signal analytics already reads.
    #
    # Sorted by distance rather than by the search page's blended `best` score, and only when
    # a position is actually known. The two surfaces are answering different questions: the
    # search page is asked "where can I get this", and weighs price and reputation into that;
    # the assistant is asked "who NEAREST has this", almost always in those words. Answering
    # that with a pharmacy that ranked first on rating would be a correct answer to a question
    # nobody asked.
    rows = public_availability_search(
        query=query,
        area=ctx.text("area"),
        latitude=latitude,
        longitude=longitude,
        sort="distance" if latitude is not None else "best",
    )
    return {
        "query": query,
        "located": latitude is not None,
        "results": [
            {
                "medicine": row["medicine"]["brand_name"],
                "strength": row["medicine"]["strength"],
                "requires_prescription": row["medicine"]["requires_prescription"],
                "pharmacy": row["pharmacy"]["name"],
                "area": row["pharmacy"]["area"],
                "city": row["pharmacy"]["city"],
                "phone": row["pharmacy"]["phone"],
                "availability": row["availability_status"],
                "available_up_to": row["available_up_to"],
                "unit_price": str(row["unit_price"]) if row["unit_price"] is not None else None,
                "price_note": row["price_note"],
                "delivery_enabled": row["pharmacy"]["delivery_enabled"],
                "distance_km": row["distance_km"],
            }
            for row in rows[:MAX_ROWS]
        ],
        "total_found": len(rows),
    }


def medicine_details(ctx: ToolContext) -> dict:
    """Catalogue facts for a named product - including whether it needs a prescription."""
    query = ctx.text("query")
    if not query:
        return {"query": "", "matches": []}
    matches = list(search_medicines(query, active_only=True, limit=MAX_ROWS))
    return {"query": query, "matches": [_medicine_summary(item) for item in matches]}


def find_pharmacies(ctx: ToolContext) -> dict:
    """
    Connected pharmacies, nearest first when we know where the person is.

    Without a position this falls back to the old ordering - on-call pharmacies, then
    alphabetical - which is the only honest answer to "which pharmacies are near me" from a
    caller whose location nobody knows. `located` says which of the two happened, so the
    reply can offer to do better rather than quietly presenting an alphabetical list as
    though it were a proximity ranking.
    """
    area = ctx.text("area") or ctx.text("query")
    qs = Pharmacy.objects.filter(is_active=True, is_public=True)
    if area:
        qs = qs.filter(area__icontains=area)

    latitude, longitude = ctx.coordinates
    distances: dict = {}
    if latitude is None:
        rows = list(qs.order_by("-is_on_call", "name")[:MAX_ROWS])
    else:
        # Ordered in Python rather than the database: distance is trigonometry over two
        # DecimalFields, and this list is the connected pharmacy network, not an unbounded
        # table. When that stops being true the fix is a bounding box on the query, not a
        # different ordering here.
        #
        # A pharmacy with no coordinates on file still appears, ranked last. Dropping it
        # would mean sharing a location silently shrinks the directory - a pharmacy that
        # never filled in its position would become invisible to exactly the people standing
        # next to it, and nothing on screen would say so.
        candidates = list(qs.order_by("-is_on_call", "name"))
        for item in candidates:
            if item.latitude is not None and item.longitude is not None:
                distances[item.id] = round(road_km(latitude, longitude, float(item.latitude), float(item.longitude)), 2)
        candidates.sort(key=lambda item: (item.id not in distances, distances.get(item.id, 0)))
        rows = candidates[:MAX_ROWS]

    return {
        "area": area,
        "located": latitude is not None,
        "pharmacies": [
            {
                "name": item.name,
                "area": item.area,
                "city": item.city,
                "phone": item.phone,
                "is_on_call": item.is_on_call,
                "delivery_enabled": item.delivery_enabled,
                "opens_at": item.opens_at.strftime("%H:%M"),
                "closes_at": item.closes_at.strftime("%H:%M"),
                "distance_km": distances.get(item.id),
            }
            for item in rows
        ],
        "total_found": qs.count(),
    }
