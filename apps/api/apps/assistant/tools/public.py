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


# Upper bound on products resolved from one "add x, y and z" message - keeps a single turn
# from fanning out into an unbounded number of availability searches.
MAX_CART_ITEMS = 8


def _resolve_cart_item(ctx: ToolContext, query: str, quantity: int, sort: str) -> dict:
    """Resolve one product name to a single orderable listing, or record why it could not be."""
    latitude, longitude = ctx.coordinates
    rows = public_availability_search(query=query, latitude=latitude, longitude=longitude, sort=sort)
    orderable = [row for row in rows if row["available_up_to"] > 0 and row["pharmacy"]["accepts_online_orders"]]
    if not orderable:
        return {
            "added": False,
            "reason": "not_orderable" if rows else "no_match",
            "query": query,
            "requested_quantity": quantity,
        }

    best = orderable[0]
    medicine = best["medicine"]
    unit_price = best["unit_price"]
    granted = min(quantity, best["available_up_to"])
    return {
        "added": True,
        "query": query,
        "requested_quantity": quantity,
        "granted_quantity": granted,
        "basis": "price" if sort == "price" else "relevance",
        "total_listings": len(orderable),
        "match": {
            "medicine_id": str(medicine["id"]),
            "name": f"{medicine['brand_name']} {medicine['strength']}".strip(),
            "generic": medicine["generic_name"] or None,
            "image": medicine["image"],
            "unit_price": str(unit_price) if unit_price is not None else None,
            "requires_prescription": bool(medicine["requires_prescription"]),
            "availability": best["availability_status"],
            "available_up_to": best["available_up_to"],
        },
    }


def _requested_queries(ctx: ToolContext) -> list[str]:
    """The product names to resolve this turn: the `queries` list if present, else `query`."""
    raw = ctx.slots.get("queries")
    names = []
    if isinstance(raw, (list, tuple)):
        names = [item.strip() for item in raw if isinstance(item, str) and item.strip()]
    if not names:
        single = ctx.text("query")
        names = [single] if single else []
    # De-duplicate while keeping order, so "add panadol and panadol" resolves once.
    seen: set[str] = set()
    unique = []
    for name in names:
        key = name.lower()
        if key not in seen:
            seen.add(key)
            unique.append(name)
    return unique[:MAX_CART_ITEMS]


def cart_add(ctx: ToolContext) -> dict:
    """
    Resolve one or more products - and optionally "the cheapest" of each - to orderable listings.

    Writes nothing. The cart lives in the browser (apps/web/lib/basket.ts), so all this does
    is the lookup the shopper would otherwise do by hand: run the same ranked public search
    the shop page uses, drop anything that cannot actually be ordered online right now, and
    hand back the best row per product for the web client to add. The reply the person sees is
    rendered from this dict by apps.assistant.intents.render_cart_add and is never composed,
    so the product names and quantities they are told they can undo are exactly these.

    A single-product request returns the flat `{"added": ..., "match": ...}` shape; a
    multi-product one returns `{"multi": True, "results": [<that shape>, ...]}`.
    """
    quantity = ctx.number("quantity", 1, low=1, high=20)
    # "cheapest" flips the sort to price; anything else keeps the blended relevance ranking
    # (distance, reputation, then price) the shop page defaults to.
    sort = "price" if ctx.text("sort") == "price" else "best"

    queries = _requested_queries(ctx)
    if not queries:
        return {"added": False, "reason": "no_query", "query": "", "requested_quantity": quantity}

    if len(queries) == 1:
        return _resolve_cart_item(ctx, queries[0], quantity, sort)

    results = [_resolve_cart_item(ctx, name, quantity, sort) for name in queries]
    return {
        "multi": True,
        "query": ", ".join(queries),
        "basis": "price" if sort == "price" else "relevance",
        "added_any": any(row.get("added") for row in results),
        "results": results,
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
