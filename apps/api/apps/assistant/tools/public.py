"""
Lookups any visitor may run, signed in or not.

Nothing here touches a personal record: it is the public catalogue and the public availability
view, the same data the unauthenticated /api/public/search/ endpoint already serves. That is
why these are the guest persona's entire toolset - there is nothing to leak.
"""

from __future__ import annotations

from apps.assistant.tools.base import ToolContext
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
    """Which connected pharmacies currently have a medicine, cheapest/nearest first."""
    query = ctx.text("query")
    if not query:
        return {"query": "", "results": []}

    # Reuses the ranked public search rather than querying InventoryBatch directly, so the
    # assistant is subject to exactly the same public quantity caps, price-regime handling and
    # unmet-demand recording as the search page. An answer here and an answer there can never
    # disagree, and a miss still feeds the unmet-demand signal analytics already reads.
    rows = public_availability_search(query=query, area=ctx.text("area"))
    return {
        "query": query,
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
    """Connected pharmacies, optionally narrowed to an area the person named."""
    area = ctx.text("area") or ctx.text("query")
    qs = Pharmacy.objects.filter(is_active=True, is_public=True)
    if area:
        qs = qs.filter(area__icontains=area)
    rows = qs.order_by("-is_on_call", "name")[:MAX_ROWS]
    return {
        "area": area,
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
            }
            for item in rows
        ],
        "total_found": qs.count(),
    }
