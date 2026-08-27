"""
Smart Insights: a plain-language synthesis layer over the KPI functions in
apps/analytics/services/kpis.py, for pharmacy owners who don't want to read four tabs of
numbers to find out what needs attention today.

Deliberately rule-based, not an LLM call. Every insight below is a template filled from a
number `kpis` already computed deterministically - no external API, no per-request cost, and
no risk of inventing a figure the pharmacy didn't actually earn. See docs/AI_FEATURES.md §5
for the "do we need an external provider" answer this implements: not for v1. A future
free-form natural-language digest or Q&A layer (also cataloged there) is the point where an
LLM provider would actually earn its cost - this endpoint is not that, on purpose.

Severity:
  critical     needs action today (expiry about to bite, many SKUs below reorder point)
  warning      needs attention this week
  opportunity  upside, not a problem (unmet demand nearby for something not stocked)
  info         context, no action implied
"""

from __future__ import annotations

from apps.analytics.services import kpis

SEVERITY_ORDER = {"critical": 0, "warning": 1, "opportunity": 2, "info": 3}


def _expiry_insight(stock: dict) -> dict | None:
    if stock["units_expiring_30d"]:
        return {
            "id": "expiry-30d",
            "severity": "critical",
            "category": "inventory",
            "title": f'{stock["units_expiring_30d"]} units expiring within 30 days',
            "detail": f'Worth {stock["value_expiring_30d"]} at retail — consider a markdown or a transfer before it becomes a write-off.',
            "metric": float(stock["value_expiring_30d"]),
        }
    if stock["units_expiring_60d"]:
        return {
            "id": "expiry-60d",
            "severity": "warning",
            "category": "inventory",
            "title": f'{stock["units_expiring_60d"]} units expiring within 60 days',
            "detail": f'Worth {stock["value_expiring_60d"]} at retail — plan ahead before the 30-day window.',
            "metric": float(stock["value_expiring_60d"]),
        }
    return None


def _reorder_insight(replenishment: dict) -> dict | None:
    if not replenishment["reorder_now_count"]:
        return None
    top = [row["name"] for row in replenishment["suggestions"] if row["needs_reorder"]][:3]
    return {
        "id": "reorder-now",
        "severity": "critical" if replenishment["reorder_now_count"] >= 5 else "warning",
        "category": "replenishment",
        "title": f'{replenishment["reorder_now_count"]} SKUs are at or below their reorder point',
        "detail": ("Top of the list: " + ", ".join(top)) if top else "",
        "metric": replenishment["reorder_now_count"],
    }


def _dead_stock_insight(movement: dict) -> dict | None:
    dead = movement["dead_stock"]
    if not dead:
        return None
    dead_value = sum(row["value_at_cost"] for row in dead)
    if not dead_value:
        return None
    return {
        "id": "dead-stock",
        "severity": "warning",
        "category": "inventory",
        "title": f'{dead_value} tied up in stock with no sale in {movement["dead_stock_days"]} days',
        "detail": f'{len(dead)} SKU(s) affected, led by {dead[0]["name"]}.',
        "metric": float(dead_value),
    }


def _unmet_demand_insight(demand: dict) -> dict | None:
    missed = [row for row in demand["signals"] if not row["you_stock_it"]]
    if not missed:
        return None
    top = missed[0]
    return {
        "id": "unmet-demand",
        "severity": "opportunity",
        "category": "demand",
        "title": f'{top["requests"]} nearby search(es) for {top["name"]} you don’t stock',
        "detail": f'{len(missed)} unstocked item(s) had unmet demand in {demand["area"]} over the last {demand["window_days"]} days.',
        "metric": top["requests"],
    }


def _low_stock_insight(stock: dict) -> dict | None:
    if not stock["low_stock_skus"]:
        return None
    return {
        "id": "low-stock",
        "severity": "warning",
        "category": "inventory",
        "title": f'{stock["low_stock_skus"]} SKUs are running low',
        "detail": f'{stock["out_of_stock_batches"]} batch(es) are already at zero.',
        "metric": stock["low_stock_skus"],
    }


def _margin_mix_insight(sales: dict) -> dict | None:
    if not sales["revenue"] or sales["regulated_share_percent"] < 70:
        return None
    return {
        "id": "regulated-heavy-mix",
        "severity": "info",
        "category": "commercial",
        "title": f'{sales["regulated_share_percent"]}% of revenue is MoPH-regulated',
        "detail": "Margin is only steerable on the free-priced share — supplements/parapharmacy is where mix improvements move the needle.",
        "metric": sales["regulated_share_percent"],
    }


def _gmroi_insight(turnover: dict) -> dict | None:
    if not turnover["inventory_turnover"] or turnover["gmroi"] >= 1:
        return None
    return {
        "id": "low-gmroi",
        "severity": "warning",
        "category": "commercial",
        "title": f'GMROI is {turnover["gmroi"]} — each dollar of stock is earning less than a dollar of margin',
        "detail": f'Inventory turnover is {turnover["inventory_turnover"]}x over the last {turnover["window_days"]} days.',
        "metric": turnover["gmroi"],
    }


def _acceptance_rate_insight(platform: dict) -> dict | None:
    if not platform["orders_received"] or platform["acceptance_rate_percent"] >= 80:
        return None
    return {
        "id": "low-acceptance",
        "severity": "warning",
        "category": "platform",
        "title": f'Order acceptance rate is {platform["acceptance_rate_percent"]}%',
        "detail": f'{platform["orders_rejected"]} of {platform["orders_received"]} orders were rejected in the last {platform["window_days"]} days — this weighs against you in future sourcing.',
        "metric": platform["acceptance_rate_percent"],
    }


def generate_insights(pharmacy, *, limit: int = 8) -> list[dict]:
    stock = kpis.stock_snapshot(pharmacy)
    replenishment = kpis.replenishment_plan(pharmacy)
    movement = kpis.movement_classification(pharmacy)
    demand = kpis.demand_signals(pharmacy)
    sales = kpis.sales_snapshot(pharmacy, days=30)
    turnover = kpis.turnover_metrics(pharmacy)
    platform = kpis.platform_performance(pharmacy)

    candidates = [
        _expiry_insight(stock),
        _reorder_insight(replenishment),
        _dead_stock_insight(movement),
        _unmet_demand_insight(demand),
        _low_stock_insight(stock),
        _margin_mix_insight(sales),
        _gmroi_insight(turnover),
        _acceptance_rate_insight(platform),
    ]
    insights = [item for item in candidates if item is not None]
    insights.sort(key=lambda item: SEVERITY_ORDER[item["severity"]])
    return insights[:limit]
