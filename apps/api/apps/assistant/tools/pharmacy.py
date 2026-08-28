"""
One pharmacy's own operations.

Every queryset is anchored on `ctx.user.pharmacy`, which is the same tenant boundary
apps.accounts.permissions.IsPharmacyUserWithActivePharmacy enforces on the workspace endpoints.
Staff at pharmacy A cannot reach pharmacy B's stock, sales or orders through the assistant for
the same reason they cannot reach it through the API: the filter is applied before anything
the person typed is considered.
"""

from __future__ import annotations

from apps.analytics.services.insights import generate_insights
from apps.analytics.services.kpis import sales_snapshot, stock_snapshot
from apps.assistant.tools.base import ToolContext
from apps.inventory.models import InventoryBatch
from apps.orders.models import OrderFulfillment

MAX_ROWS = 6


def _pharmacy(ctx: ToolContext):
    return getattr(ctx.user, "pharmacy", None)


def stock_lookup(ctx: ToolContext) -> dict:
    """How much of a named product this pharmacy holds, batch by batch."""
    pharmacy = _pharmacy(ctx)
    query = ctx.text("query")
    if pharmacy is None or not query:
        return {"query": query, "batches": [], "total_quantity": 0}

    qs = (
        InventoryBatch.objects.filter(pharmacy=pharmacy, is_archived=False)
        .filter(medicine__brand_name__icontains=query)
        .select_related("medicine")
        .order_by("expiry_date")
    )
    batches = list(qs[:MAX_ROWS])
    return {
        "query": query,
        "batches": [
            {
                "medicine": str(item.medicine),
                "quantity": item.current_quantity,
                "reserved": item.reserved_quantity,
                "expiry_date": item.expiry_date.isoformat() if item.expiry_date else None,
                "selling_price": str(item.selling_price),
                "is_low_stock": item.is_low_stock,
                "is_expiring_soon": item.is_expiring_soon,
            }
            for item in batches
        ],
        "total_quantity": sum(item.current_quantity for item in batches),
        "total_found": qs.count(),
    }


def stock_alerts(ctx: ToolContext) -> dict:
    """What is running low or approaching expiry."""
    pharmacy = _pharmacy(ctx)
    if pharmacy is None:
        return {"low_stock": [], "expiring_soon": [], "low_stock_count": 0, "expiring_count": 0}

    batches = list(InventoryBatch.objects.filter(pharmacy=pharmacy, is_archived=False).select_related("medicine"))
    low = [item for item in batches if item.is_low_stock]
    expiring = [item for item in batches if item.is_expiring_soon]
    return {
        "low_stock": [{"medicine": str(item.medicine), "quantity": item.current_quantity, "threshold": item.low_stock_threshold} for item in low[:MAX_ROWS]],
        "expiring_soon": [
            {"medicine": str(item.medicine), "quantity": item.current_quantity, "expiry_date": item.expiry_date.isoformat() if item.expiry_date else None}
            for item in sorted(expiring, key=lambda b: b.expiry_date or b.created_at.date())[:MAX_ROWS]
        ],
        "low_stock_count": len(low),
        "expiring_count": len(expiring),
    }


def sales_summary(ctx: ToolContext) -> dict:
    """How the pharmacy traded over a recent window."""
    pharmacy = _pharmacy(ctx)
    if pharmacy is None:
        return {"days": 0, "sales": {}, "stock": {}}

    days = ctx.number("days", 30, low=1, high=365)
    # Both snapshots come straight from the analytics service the pharmacy's own dashboard
    # renders, so a number quoted in chat and the same number on the Analytics screen are
    # computed once, in one place, and cannot drift apart.
    return {"days": days, "sales": sales_snapshot(pharmacy, days=days), "stock": stock_snapshot(pharmacy)}


def business_insights(ctx: ToolContext) -> dict:
    """The ranked findings the analytics screen already computes for this pharmacy."""
    pharmacy = _pharmacy(ctx)
    if pharmacy is None:
        return {"insights": []}
    return {"insights": generate_insights(pharmacy, limit=MAX_ROWS)}


def incoming_orders(ctx: ToolContext) -> dict:
    """Online orders waiting on this pharmacy to act."""
    pharmacy = _pharmacy(ctx)
    if pharmacy is None:
        return {"waiting": [], "waiting_count": 0}

    qs = (
        OrderFulfillment.objects.filter(pharmacy=pharmacy, status__in=[OrderFulfillment.Status.PENDING, OrderFulfillment.Status.ACCEPTED])
        .select_related("order")
        .order_by("created_at")
    )
    rows = list(qs[:MAX_ROWS])
    return {
        "waiting": [
            {
                "reference": item.order.reference,
                "status": item.get_status_display(),
                "subtotal": str(item.subtotal),
                "fulfillment_type": item.order.fulfillment_type,
                "placed_at": item.order.created_at.isoformat(),
                "line_count": item.lines.count(),
            }
            for item in rows
        ],
        "waiting_count": qs.count(),
    }
