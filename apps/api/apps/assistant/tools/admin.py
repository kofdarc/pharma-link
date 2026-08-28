"""
Platform-wide operational state, for administrators.

Deliberately aggregate. Nothing here returns a prescription, a diagnosis note or an individual
patient's order history: an administrator's job on this platform is running the network, and
the assistant's reach is scoped to that rather than to everything the admin role could
technically be granted. Counts, applications, dispatch load and the audit trail.
"""

from __future__ import annotations

from django.utils import timezone

from apps.assistant.tools.base import ToolContext
from apps.audit.models import AuditLog
from apps.delivery.models import DeliveryRoute, Driver
from apps.orders.models import Order
from apps.pharmacies.models import Pharmacy, PharmacyApplication

MAX_ROWS = 6

# An order nobody is waiting on any more. PARTIALLY_CANCELLED is deliberately absent: part of
# it is still live and still someone's problem.
CLOSED_ORDER_STATUSES = [Order.Status.DELIVERED, Order.Status.COLLECTED, Order.Status.CANCELLED, Order.Status.EXPIRED]


def platform_overview(ctx: ToolContext) -> dict:
    """The current shape of the network."""
    today = timezone.localdate()
    return {
        "pharmacies_active": Pharmacy.objects.filter(is_active=True).count(),
        "pharmacies_accepting_orders": Pharmacy.objects.filter(is_active=True, accepts_online_orders=True).count(),
        "applications_pending": PharmacyApplication.objects.filter(status=PharmacyApplication.Status.PENDING).count(),
        "orders_today": Order.objects.filter(created_at__date=today).count(),
        "orders_open": Order.objects.exclude(status__in=CLOSED_ORDER_STATUSES).count(),
        "drivers_online": Driver.objects.filter(is_active=True, is_online=True).count(),
    }


def pending_applications(ctx: ToolContext) -> dict:
    """Pharmacies waiting on review, oldest first - the ones going stale are the point."""
    qs = PharmacyApplication.objects.filter(status=PharmacyApplication.Status.PENDING).order_by("created_at")
    rows = list(qs[:MAX_ROWS])
    now = timezone.now()
    return {
        "applications": [
            {
                "pharmacy_name": item.pharmacy_name,
                "owner_name": item.owner_name,
                "area": item.area,
                "city": item.city,
                "submitted_at": item.created_at.isoformat(),
                "waiting_days": (now - item.created_at).days,
            }
            for item in rows
        ],
        "pending_count": qs.count(),
    }


def dispatch_snapshot(ctx: ToolContext) -> dict:
    """Delivery load right now: routes in flight, and orders with nobody assigned."""
    unassigned = Order.objects.filter(status__in=[Order.Status.CONFIRMED, Order.Status.READY], fulfillment_type=Order.FulfillmentType.DELIVERY).exclude(
        route_stops__isnull=False
    )
    return {
        "routes_active": DeliveryRoute.objects.filter(status=DeliveryRoute.Status.ACTIVE).count(),
        "routes_proposed": DeliveryRoute.objects.filter(status__in=[DeliveryRoute.Status.PROPOSED, DeliveryRoute.Status.OFFERED]).count(),
        "drivers_online": Driver.objects.filter(is_active=True, is_online=True).count(),
        "orders_awaiting_driver": unassigned.distinct().count(),
        "orders_in_transit": Order.objects.filter(status=Order.Status.IN_TRANSIT).count(),
    }


def recent_activity(ctx: ToolContext) -> dict:
    """The tail of the audit trail."""
    qs = AuditLog.objects.select_related("pharmacy").order_by("-created_at")
    rows = list(qs[:MAX_ROWS])
    return {
        "entries": [
            {
                "action": item.action,
                "summary": item.summary[:200],
                "pharmacy": item.pharmacy.name if item.pharmacy_id else None,
                "created_at": item.created_at.isoformat(),
            }
            for item in rows
        ]
    }
