"""
Pharmacy analytics.

The metric set follows what community pharmacy operators and their wholesalers actually
review, rather than generic e-commerce dashboards:

  Inventory health   stock-on-hand at cost and retail, inventory turnover, days of
                     inventory outstanding (DIO), GMROI, dead stock, expiry exposure
  Movement           ABC / Pareto classification, fast vs slow movers, unit velocity
  Replenishment      average daily demand, demand variability, safety stock and reorder
                     point (the classic ROP = mu*L + z*sigma*sqrt(L))
  Commercial         revenue, gross margin, margin %, average basket, transactions/day,
                     regulated vs free-priced revenue split (margin is only steerable on
                     the free-priced half, which is the whole point of separating them)
  Demand you missed  unmet demand from searches and baskets the network could not fill -
                     data a till system structurally cannot produce

Everything is computed from StockMovement + Sale history, so it works the same whether
stock arrived by CSV import, manual entry, or the integration bridge.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from statistics import pstdev

from django.db.models import Avg, Count, DecimalField, ExpressionWrapper, F, Q, Sum
from django.utils import timezone

from apps.inventory.models import InventoryBatch, StockMovement
from apps.medicines.models import PriceRegime
from apps.orders.models import OrderFulfillment, UnmetDemandSignal
from apps.sales.models import Sale, SaleItem

# Service level 95% -> z = 1.645. Pharmacies rarely accept lower on chronic medication.
SAFETY_STOCK_Z = 1.645
DEFAULT_LEAD_TIME_DAYS = 3
DEAD_STOCK_DAYS = 90
ZERO = Decimal("0")


def _decimal(value) -> Decimal:
    return Decimal(str(value)) if value is not None else ZERO


def _money(value) -> Decimal:
    return _decimal(value).quantize(Decimal("0.01"))


def stock_snapshot(pharmacy) -> dict:
    today = timezone.localdate()
    live = InventoryBatch.objects.filter(pharmacy=pharmacy, is_archived=False)

    at_cost = live.aggregate(
        value=Sum(ExpressionWrapper(F("current_quantity") * F("purchase_cost"), output_field=DecimalField(max_digits=16, decimal_places=2)))
    )["value"]
    at_retail = live.aggregate(
        value=Sum(ExpressionWrapper(F("current_quantity") * F("selling_price"), output_field=DecimalField(max_digits=16, decimal_places=2)))
    )["value"]

    expiring = {}
    for horizon in (30, 60, 90):
        window = live.filter(expiry_date__gte=today, expiry_date__lte=today + timedelta(days=horizon))
        expiring[f"value_expiring_{horizon}d"] = _money(
            window.aggregate(value=Sum(ExpressionWrapper(F("current_quantity") * F("selling_price"), output_field=DecimalField(max_digits=16, decimal_places=2))))["value"]
        )
        expiring[f"units_expiring_{horizon}d"] = window.aggregate(units=Sum("current_quantity"))["units"] or 0

    expired = live.filter(expiry_date__lt=today)
    batches = list(live.select_related("medicine"))
    return {
        "sku_count": live.values("medicine_id").distinct().count(),
        "batch_count": live.count(),
        "units_on_hand": live.aggregate(units=Sum("current_quantity"))["units"] or 0,
        "units_reserved": live.aggregate(units=Sum("reserved_quantity"))["units"] or 0,
        "stock_value_at_cost": _money(at_cost),
        "stock_value_at_retail": _money(at_retail),
        "potential_margin_value": _money(_decimal(at_retail) - _decimal(at_cost)),
        "low_stock_skus": sum(1 for batch in batches if batch.is_low_stock),
        "out_of_stock_batches": live.filter(current_quantity=0).count(),
        "expired_batches": expired.count(),
        "expired_value_at_cost": _money(
            expired.aggregate(value=Sum(ExpressionWrapper(F("current_quantity") * F("purchase_cost"), output_field=DecimalField(max_digits=16, decimal_places=2))))["value"]
        ),
        **expiring,
    }


def sales_snapshot(pharmacy, *, days: int = 30) -> dict:
    since = timezone.now() - timedelta(days=days)
    sales = Sale.objects.filter(pharmacy=pharmacy, status=Sale.Status.COMPLETED, sale_datetime__gte=since)
    totals = sales.aggregate(revenue=Sum("total"), transactions=Count("id"), discount=Sum("discount_total"))
    revenue = _decimal(totals["revenue"])
    transactions = totals["transactions"] or 0

    items = SaleItem.objects.filter(sale__in=sales).select_related("inventory_batch", "medicine")
    cogs = ZERO
    units = 0
    regulated_revenue = ZERO
    free_revenue = ZERO
    for item in items:
        units += item.quantity
        cost = item.inventory_batch.purchase_cost if item.inventory_batch and item.inventory_batch.purchase_cost is not None else None
        if cost is not None:
            cogs += _decimal(cost) * item.quantity
        if item.medicine.price_regime == PriceRegime.REGULATED:
            regulated_revenue += _decimal(item.line_total)
        else:
            free_revenue += _decimal(item.line_total)

    gross_margin = revenue - cogs
    channel_split = dict(
        sales.values_list("channel").annotate(total=Sum("total")).values_list("channel", "total")
    )
    return {
        "window_days": days,
        "revenue": _money(revenue),
        "cogs": _money(cogs),
        "gross_margin": _money(gross_margin),
        "gross_margin_percent": float(round(gross_margin / revenue * 100, 2)) if revenue else 0.0,
        "transactions": transactions,
        "units_sold": units,
        "average_basket": _money(revenue / transactions) if transactions else ZERO,
        "average_units_per_basket": round(units / transactions, 2) if transactions else 0.0,
        "transactions_per_day": round(transactions / days, 2),
        "discount_given": _money(totals["discount"]),
        "regulated_revenue": _money(regulated_revenue),
        "free_priced_revenue": _money(free_revenue),
        "regulated_share_percent": float(round(regulated_revenue / revenue * 100, 1)) if revenue else 0.0,
        "revenue_by_channel": {key: _money(value) for key, value in channel_split.items()},
    }


def turnover_metrics(pharmacy, *, days: int = 90) -> dict:
    """
    Inventory turnover = COGS / average inventory at cost. DIO = days / turnover.
    GMROI = gross margin / average inventory at cost: the number a wholesaler asks about,
    because it says how much margin each pound of stock earns.
    """
    since = timezone.now() - timedelta(days=days)
    sales = Sale.objects.filter(pharmacy=pharmacy, status=Sale.Status.COMPLETED, sale_datetime__gte=since)
    items = SaleItem.objects.filter(sale__in=sales).select_related("inventory_batch")

    cogs = ZERO
    revenue = ZERO
    for item in items:
        revenue += _decimal(item.line_total)
        if item.inventory_batch and item.inventory_batch.purchase_cost is not None:
            cogs += _decimal(item.inventory_batch.purchase_cost) * item.quantity

    current_value = _decimal(
        InventoryBatch.objects.filter(pharmacy=pharmacy, is_archived=False).aggregate(
            value=Sum(ExpressionWrapper(F("current_quantity") * F("purchase_cost"), output_field=DecimalField(max_digits=16, decimal_places=2)))
        )["value"]
    )
    # Opening stock is approximated from current stock plus what left in the window: enough
    # for a POC, and the shape a real snapshot table would replace.
    average_inventory = (current_value + current_value + cogs) / 2 if current_value else ZERO
    turnover = float(round(cogs / average_inventory, 2)) if average_inventory else 0.0
    annualised = round(turnover * (365 / days), 2)
    return {
        "window_days": days,
        "cogs": _money(cogs),
        "average_inventory_at_cost": _money(average_inventory),
        "inventory_turnover": turnover,
        "inventory_turnover_annualised": annualised,
        "days_inventory_outstanding": round(days / turnover, 1) if turnover else None,
        "gmroi": float(round((revenue - cogs) / average_inventory, 2)) if average_inventory else 0.0,
        "sell_through_percent": float(round(cogs / (cogs + current_value) * 100, 1)) if (cogs + current_value) else 0.0,
    }


def movement_classification(pharmacy, *, days: int = 90, limit: int = 40) -> dict:
    """
    ABC/Pareto on revenue: A = top 80% of revenue, B = next 15%, C = the tail.
    Also flags dead stock, which is where a pharmacy's cash is quietly trapped.
    """
    since = timezone.now() - timedelta(days=days)
    rows = list(
        SaleItem.objects.filter(sale__pharmacy=pharmacy, sale__status=Sale.Status.COMPLETED, sale__sale_datetime__gte=since)
        .values("medicine_id", "medicine__brand_name", "medicine__strength", "medicine__form")
        .annotate(units=Sum("quantity"), revenue=Sum("line_total"), lines=Count("id"))
        .order_by("-revenue")
    )
    total_revenue = sum(_decimal(row["revenue"]) for row in rows) or ZERO

    classified = []
    cumulative = ZERO
    for row in rows:
        cumulative += _decimal(row["revenue"])
        share = float(cumulative / total_revenue * 100) if total_revenue else 0.0
        grade = "A" if share <= 80 else ("B" if share <= 95 else "C")
        classified.append(
            {
                "medicine_id": row["medicine_id"],
                "name": " ".join(filter(None, [row["medicine__brand_name"], row["medicine__strength"], row["medicine__form"]])),
                "units": row["units"],
                "revenue": _money(row["revenue"]),
                "revenue_share_percent": round(float(_decimal(row["revenue"]) / total_revenue * 100), 2) if total_revenue else 0.0,
                "cumulative_share_percent": round(share, 2),
                "abc_class": grade,
                "daily_velocity": round(row["units"] / days, 3),
            }
        )

    sold_ids = {row["medicine_id"] for row in rows}
    dead_cutoff = timezone.now() - timedelta(days=DEAD_STOCK_DAYS)
    moved_recently = set(
        StockMovement.objects.filter(pharmacy=pharmacy, movement_type=StockMovement.MovementType.SALE, created_at__gte=dead_cutoff).values_list("medicine_id", flat=True)
    )
    dead = (
        InventoryBatch.objects.filter(pharmacy=pharmacy, is_archived=False, current_quantity__gt=0)
        .exclude(medicine_id__in=moved_recently)
        .values("medicine_id", "medicine__brand_name", "medicine__strength")
        .annotate(units=Sum("current_quantity"), value=Sum(ExpressionWrapper(F("current_quantity") * F("purchase_cost"), output_field=DecimalField(max_digits=16, decimal_places=2))))
        .order_by("-value")[:limit]
    )
    return {
        "window_days": days,
        "counts": {
            "A": sum(1 for row in classified if row["abc_class"] == "A"),
            "B": sum(1 for row in classified if row["abc_class"] == "B"),
            "C": sum(1 for row in classified if row["abc_class"] == "C"),
        },
        "top_movers": classified[:limit],
        "slow_movers": [row for row in classified if row["abc_class"] == "C"][-limit:],
        "dead_stock": [
            {
                "medicine_id": row["medicine_id"],
                "name": " ".join(filter(None, [row["medicine__brand_name"], row["medicine__strength"]])),
                "units": row["units"],
                "value_at_cost": _money(row["value"]),
            }
            for row in dead
        ],
        "dead_stock_days": DEAD_STOCK_DAYS,
        "skus_with_no_sales": InventoryBatch.objects.filter(pharmacy=pharmacy, is_archived=False, current_quantity__gt=0)
        .exclude(medicine_id__in=sold_ids)
        .values("medicine_id")
        .distinct()
        .count(),
    }


def replenishment_plan(pharmacy, *, days: int = 60, lead_time_days: int = DEFAULT_LEAD_TIME_DAYS, limit: int = 40) -> dict:
    """
    Reorder point per SKU:  ROP = daily_demand * lead_time + safety_stock
                            safety_stock = z * sigma_daily * sqrt(lead_time)
    Anything already below its ROP is a buy-now line.
    """
    since = timezone.localdate() - timedelta(days=days)
    daily_rows = (
        SaleItem.objects.filter(sale__pharmacy=pharmacy, sale__status=Sale.Status.COMPLETED, sale__sale_datetime__date__gte=since)
        .values("medicine_id", "sale__sale_datetime__date")
        .annotate(units=Sum("quantity"))
    )
    per_medicine: dict = {}
    for row in daily_rows:
        per_medicine.setdefault(row["medicine_id"], []).append(row["units"])

    on_hand = {
        row["medicine_id"]: row["units"]
        for row in InventoryBatch.objects.filter(pharmacy=pharmacy, is_archived=False)
        .values("medicine_id")
        .annotate(units=Sum("current_quantity"))
    }
    names = {
        row["medicine_id"]: " ".join(filter(None, [row["medicine__brand_name"], row["medicine__strength"], row["medicine__form"]]))
        for row in InventoryBatch.objects.filter(pharmacy=pharmacy).values("medicine_id", "medicine__brand_name", "medicine__strength", "medicine__form")
    }

    suggestions = []
    for medicine_id, observations in per_medicine.items():
        # Days with no sale are real zeros; ignoring them would overstate demand.
        series = observations + [0] * max(0, days - len(observations))
        daily_demand = sum(series) / days
        variability = pstdev(series) if len(series) > 1 else 0.0
        safety_stock = SAFETY_STOCK_Z * variability * (lead_time_days**0.5)
        reorder_point = daily_demand * lead_time_days + safety_stock
        stock = on_hand.get(medicine_id, 0)
        days_cover = round(stock / daily_demand, 1) if daily_demand else None
        suggestions.append(
            {
                "medicine_id": medicine_id,
                "name": names.get(medicine_id, ""),
                "units_on_hand": stock,
                "avg_daily_demand": round(daily_demand, 2),
                "demand_std_dev": round(variability, 2),
                "safety_stock": int(round(safety_stock)),
                "reorder_point": int(round(reorder_point)),
                "days_of_cover": days_cover,
                "suggested_order_quantity": max(0, int(round(reorder_point + daily_demand * days / 4 - stock))),
                "needs_reorder": stock <= reorder_point,
            }
        )
    suggestions.sort(key=lambda row: (not row["needs_reorder"], row["days_of_cover"] if row["days_of_cover"] is not None else 9999))
    return {
        "window_days": days,
        "lead_time_days": lead_time_days,
        "service_level_percent": 95,
        "reorder_now_count": sum(1 for row in suggestions if row["needs_reorder"]),
        "suggestions": suggestions[:limit],
    }


def demand_signals(pharmacy, *, days: int = 30, limit: int = 20) -> dict:
    """Demand a till never sees: searches and baskets nobody nearby could fill."""
    since = timezone.now() - timedelta(days=days)
    area_filter = Q(area__iexact=pharmacy.area) | Q(area__iexact=pharmacy.city)
    rows = (
        UnmetDemandSignal.objects.filter(area_filter, created_at__gte=since, medicine__isnull=False)
        .values("medicine_id", "medicine__brand_name", "medicine__strength", "source")
        .annotate(requests=Count("id"), units=Sum("quantity_requested"))
        .order_by("-requests")[:limit]
    )
    stocked = set(
        InventoryBatch.objects.filter(pharmacy=pharmacy, is_archived=False, current_quantity__gt=0).values_list("medicine_id", flat=True)
    )
    return {
        "window_days": days,
        "area": pharmacy.area,
        "signals": [
            {
                "medicine_id": row["medicine_id"],
                "name": " ".join(filter(None, [row["medicine__brand_name"], row["medicine__strength"]])),
                "requests": row["requests"],
                "units_requested": row["units"],
                "source": row["source"],
                "you_stock_it": row["medicine_id"] in stocked,
            }
            for row in rows
        ],
    }


def platform_performance(pharmacy, *, days: int = 30) -> dict:
    since = timezone.now() - timedelta(days=days)
    slices = OrderFulfillment.objects.filter(pharmacy=pharmacy, created_at__gte=since)
    accepted = slices.exclude(status__in=[OrderFulfillment.Status.PENDING, OrderFulfillment.Status.REJECTED])
    acceptance_times = [
        (row.accepted_at - row.created_at).total_seconds() / 60
        for row in slices.filter(accepted_at__isnull=False)
    ]
    return {
        "window_days": days,
        "orders_received": slices.count(),
        "orders_accepted": accepted.count(),
        "orders_rejected": slices.filter(status=OrderFulfillment.Status.REJECTED).count(),
        "acceptance_rate_percent": round(accepted.count() / slices.count() * 100, 1) if slices.count() else 0.0,
        "median_acceptance_minutes": round(sorted(acceptance_times)[len(acceptance_times) // 2], 1) if acceptance_times else None,
        "shared_orders": slices.filter(order__fulfillments__isnull=False).exclude(order__fulfillments__pharmacy=pharmacy).values("order_id").distinct().count(),
        "rating_average": float(pharmacy.rating_average),
        "rating_count": pharmacy.rating_count,
        "fulfillment_success_rate": float(pharmacy.fulfillment_success_rate),
    }


def revenue_timeseries(pharmacy, *, days: int = 30) -> list[dict]:
    since = timezone.localdate() - timedelta(days=days - 1)
    rows = (
        Sale.objects.filter(pharmacy=pharmacy, status=Sale.Status.COMPLETED, sale_datetime__date__gte=since)
        .values("sale_datetime__date")
        .annotate(revenue=Sum("total"), transactions=Count("id"))
        .order_by("sale_datetime__date")
    )
    by_date = {row["sale_datetime__date"]: row for row in rows}
    series = []
    for offset in range(days):
        day = since + timedelta(days=offset)
        row = by_date.get(day)
        series.append(
            {
                "date": day.isoformat(),
                "revenue": _money(row["revenue"]) if row else ZERO,
                "transactions": row["transactions"] if row else 0,
            }
        )
    return series


def overview(pharmacy) -> dict:
    return {
        "pharmacy": {"id": pharmacy.id, "name": pharmacy.name, "area": pharmacy.area},
        "generated_at": timezone.now(),
        "stock": stock_snapshot(pharmacy),
        "sales_30d": sales_snapshot(pharmacy, days=30),
        "sales_7d": sales_snapshot(pharmacy, days=7),
        "turnover": turnover_metrics(pharmacy),
        "platform": platform_performance(pharmacy),
        "revenue_series": revenue_timeseries(pharmacy, days=30),
    }
