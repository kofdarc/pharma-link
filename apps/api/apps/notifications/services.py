"""
The in-app notification feed: "what happened that this person should know about",
computed on demand from the same records the workspace screens already read.

There is no notification model. The web client polls this every ~45s while a tab is
open, diffs the item ids against what it has already shown, and raises a toast /
browser notification for anything new. So every item needs a *stable, state-encoding
id*: `order:<uuid>:READY` and `order:<uuid>:DELIVERED` are two different
notifications for the same order, and a re-poll before the client has caught up must
return the same id rather than a fresh one.

Access is by role, and every query is anchored on the passed `user` - the same
discipline as apps.assistant.tools.*. There is no id parameter anywhere in here, so
the feed can only ever describe the caller's own work.
"""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import UserRole
from apps.analytics.services import kpis
from apps.billing.models import PharmacySubscription, PlatformServiceFee
from apps.delivery.models import DeliveryRoute, RouteStop
from apps.eprescriptions.models import Prescription, PrescriptionRenewalRequest
from apps.imports.models import InventoryImport
from apps.insurance.models import InsuranceClaim
from apps.orders.models import Order, OrderFulfillment, RecurringOrder
from apps.pharmacies.models import PharmacyApplication
from apps.prescriptions.models import PrescriptionRecord

MAX_ITEMS = 20
RECENT_DAYS = 3
EXPIRING_SOON_DAYS = 3
REFILL_SOON_HOURS = 24

# Customer-facing fulfillment states worth a popup. PENDING is the starting state
# and the internal EXPIRED/CANCELLED transitions are handled at the order level.
CUSTOMER_FULFILMENT_STATES = {
    OrderFulfillment.Status.ACCEPTED,
    OrderFulfillment.Status.READY,
    OrderFulfillment.Status.PICKED_UP,
    OrderFulfillment.Status.DELIVERED,
    OrderFulfillment.Status.COLLECTED,
    OrderFulfillment.Status.REJECTED,
    OrderFulfillment.Status.DELIVERY_FAILED,
}
DECIDED_PRESCRIPTION_STATES = [
    Prescription.Status.PARTIALLY_DISPENSED,
    Prescription.Status.FULLY_DISPENSED,
    Prescription.Status.CANCELLED,
]
TERMINAL_STOP_STATES = {RouteStop.Status.DONE, RouteStop.Status.FAILED, RouteStop.Status.SKIPPED}


def _item(item_id: str, kind: str, href: str, occurred_at, badge_count: int = 1, **params) -> dict:
    return {
        "id": item_id,
        "kind": kind,
        "href": href,
        "badge_count": badge_count,
        "occurred_at": occurred_at.isoformat() if occurred_at else None,
        "params": {key: value for key, value in params.items() if value not in (None, "")},
    }


def feed_for(user) -> list[dict]:
    builders = {
        UserRole.CUSTOMER: _customer_feed,
        UserRole.PHARMACY_OWNER: _pharmacy_feed,
        UserRole.PHARMACY_STAFF: _pharmacy_feed,
        UserRole.DOCTOR: _doctor_feed,
        UserRole.DRIVER: _driver_feed,
        UserRole.PLATFORM_ADMIN: _admin_feed,
    }
    builder = builders.get(getattr(user, "role", None))
    if builder is None:
        return []
    items = builder(user)
    items.sort(key=lambda row: row["occurred_at"] or "", reverse=True)
    return items[:MAX_ITEMS]


def _customer_feed(user) -> list[dict]:
    now = timezone.now()
    since = now - timedelta(days=RECENT_DAYS)
    items: list[dict] = []

    fulfilments = (
        OrderFulfillment.objects.filter(order__customer=user, status__in=CUSTOMER_FULFILMENT_STATES, updated_at__gte=since)
        .select_related("order", "pharmacy")
        .order_by("-updated_at")[:MAX_ITEMS]
    )
    for f in fulfilments:
        occurred = f.completed_at or f.picked_up_at or f.ready_at or f.accepted_at or f.updated_at
        items.append(
            _item(
                f"order:{f.id}:{f.status}",
                "order",
                f"/orders/{f.order_id}",
                occurred,
                reference=f.order.reference,
                pharmacy=f.pharmacy.name,
                status_label=f.get_status_display(),
            )
        )

    if user.email:
        decided = (
            Prescription.objects.filter(patient_email__iexact=user.email, updated_at__gte=since, status__in=DECIDED_PRESCRIPTION_STATES)
            .order_by("-updated_at")[:MAX_ITEMS]
        )
        for rx in decided:
            items.append(
                _item(
                    f"prescription:{rx.id}:{rx.status}",
                    "prescription_decision",
                    "/prescriptions",
                    rx.updated_at,
                    code=rx.code,
                    status_label=rx.get_status_display(),
                )
            )

    soon = now + timedelta(hours=REFILL_SOON_HOURS)
    refills = RecurringOrder.objects.filter(customer=user, is_active=True).filter(Q(next_run_at__lte=soon) | ~Q(last_error=""))
    for r in refills[:MAX_ITEMS]:
        failed = bool(r.last_error)
        items.append(
            _item(
                f"refill:{r.id}:{'error' if failed else 'due'}:{r.next_run_at.date().isoformat()}",
                "refill_failed" if failed else "refill_due",
                "/refills",
                r.updated_at,
                label=r.label,
                error=r.last_error or None,
            )
        )

    rejected_claims = InsuranceClaim.objects.filter(
        policy__customer_user=user,
        status=InsuranceClaim.Status.REJECTED,
        updated_at__gte=since,
    ).select_related("policy").order_by("-updated_at")[:MAX_ITEMS]
    for claim in rejected_claims:
        items.append(
            _item(
                f"customer-insurance-claim:{claim.id}:{claim.status}",
                "insurance_rejected",
                "/shop/insurance",
                claim.updated_at,
                holder_name=claim.policy.holder_name,
                reason=claim.rejection_reason or None,
            )
        )
    return items


def _pharmacy_feed(user) -> list[dict]:
    pharmacy = getattr(user, "pharmacy", None)
    if pharmacy is None:
        return []
    now = timezone.now()
    items: list[dict] = []

    incoming = (
        OrderFulfillment.objects.filter(pharmacy=pharmacy, status=OrderFulfillment.Status.PENDING)
        .select_related("order")
        .order_by("-created_at")[:MAX_ITEMS]
    )
    for f in incoming:
        items.append(
            _item(
                f"incoming-order:{f.id}",
                "incoming_order",
                "/pharmacy/orders",
                f.created_at,
                reference=f.order.reference,
                item_count=f.lines.count(),
                fulfillment_type=f.order.get_fulfillment_type_display(),
            )
        )

    uploads = (
        PrescriptionRecord.objects.filter(pharmacy=pharmacy, status=PrescriptionRecord.UploadStatus.PENDING_REVIEW)
        .order_by("-created_at")[:MAX_ITEMS]
    )
    for record in uploads:
        items.append(
            _item(
                f"rx-upload:{record.id}",
                "rx_upload",
                "/pharmacy/prescription-uploads",
                record.created_at,
                patient_name=record.patient_name or None,
            )
        )

    incoming_prescriptions = (
        Prescription.objects.filter(target_pharmacy=pharmacy, status=Prescription.Status.ISSUED, valid_until__gte=now)
        .select_related("doctor__user")
        .order_by("-issued_at")[:MAX_ITEMS]
    )
    for rx in incoming_prescriptions:
        items.append(
            _item(
                f"incoming-prescription:{rx.id}",
                "incoming_prescription",
                "/pharmacy/incoming-prescriptions",
                rx.issued_at,
                code=rx.code,
                patient_name=rx.patient_name,
            )
        )

    claims = InsuranceClaim.objects.filter(
        pharmacy=pharmacy, status__in=[InsuranceClaim.Status.SUBMITTED, InsuranceClaim.Status.APPROVED]
    ).select_related("policy").order_by("-updated_at")[:MAX_ITEMS]
    for claim in claims:
        items.append(
            _item(
                f"insurance-claim:{claim.id}:{claim.status}",
                "insurance_claim",
                "/pharmacy/insurance-claims",
                claim.updated_at,
                status_label=claim.get_status_display(),
                holder_name=claim.policy.holder_name,
            )
        )

    subscription = PharmacySubscription.objects.filter(pharmacy=pharmacy, status=PharmacySubscription.Status.PAST_DUE).first()
    if subscription is not None:
        items.append(
            _item(
                f"billing-subscription:{subscription.id}:{subscription.status}",
                "billing_attention",
                "/pharmacy/billing",
                subscription.updated_at,
                count=1,
            )
        )

    unpaid_fees = PlatformServiceFee.objects.filter(
        pharmacy=pharmacy, status__in=[PlatformServiceFee.Status.PENDING, PlatformServiceFee.Status.INVOICED]
    ).order_by("-created_at")[:MAX_ITEMS]
    for fee in unpaid_fees:
        items.append(
            _item(
                f"billing-fee:{fee.id}:{fee.status}",
                "billing_attention",
                "/pharmacy/billing",
                fee.updated_at,
                count=1,
            )
        )

    failed_imports = InventoryImport.objects.filter(pharmacy=pharmacy, status=InventoryImport.Status.FAILED).order_by("-updated_at")[:MAX_ITEMS]
    for inventory_import in failed_imports:
        items.append(
            _item(
                f"import-failed:{inventory_import.id}",
                "import_failed",
                f"/pharmacy/imports/{inventory_import.id}",
                inventory_import.updated_at,
                filename=inventory_import.original_filename,
            )
        )

    # Stock health is a standing condition rather than an event, so it is de-duped to
    # one notification per pharmacy per day via the date in the id.
    today = timezone.localdate().isoformat()
    stock = kpis.stock_snapshot(pharmacy)
    if stock["low_stock_skus"]:
        items.append(
            _item(
                f"stock-low:{pharmacy.id}:{today}",
                "stock_low",
                "/pharmacy/inventory",
                now,
                badge_count=stock["low_stock_skus"],
                count=stock["low_stock_skus"],
            )
        )
    if stock["units_expiring_30d"]:
        items.append(
            _item(
                f"stock-expiry:{pharmacy.id}:{today}",
                "stock_expiry",
                "/pharmacy/analytics",
                now,
                units=stock["units_expiring_30d"],
                value=str(stock["value_expiring_30d"]),
            )
        )
    return items


def _doctor_feed(user) -> list[dict]:
    doctor = getattr(user, "doctor_profile", None)
    if doctor is None:
        return []
    now = timezone.now()
    items: list[dict] = []

    pending = (
        PrescriptionRenewalRequest.objects.filter(
            prescription__doctor=doctor, status=PrescriptionRenewalRequest.Status.PENDING
        )
        .select_related("prescription", "requested_by_pharmacy")
        .order_by("-created_at")[:MAX_ITEMS]
    )
    for req in pending:
        items.append(
            _item(
                f"renewal:{req.id}",
                "renewal_request",
                "/doctor/renewal-requests",
                req.created_at,
                patient_name=req.prescription.patient_name,
                pharmacy=req.requested_by_pharmacy.name,
            )
        )

    expiring = (
        Prescription.objects.filter(
            doctor=doctor,
            status=Prescription.Status.ISSUED,
            valid_until__gte=now,
            valid_until__lte=now + timedelta(days=EXPIRING_SOON_DAYS),
        )
        .order_by("valid_until")[:MAX_ITEMS]
    )
    for rx in expiring:
        items.append(
            _item(
                f"rx-expiring:{rx.id}",
                "prescription_expiring",
                "/doctor/prescriptions",
                now,
                code=rx.code,
                patient_name=rx.patient_name,
                days_left=max(0, (rx.valid_until - now).days),
            )
        )
    return items


def _driver_feed(user) -> list[dict]:
    driver = getattr(user, "driver_profile", None)
    if driver is None:
        return []
    items: list[dict] = []

    offered = DeliveryRoute.objects.filter(driver=driver, status=DeliveryRoute.Status.OFFERED).order_by("-offered_at")
    for route in offered[:MAX_ITEMS]:
        stop_count = route.stops.count()
        items.append(
            _item(
                f"route-offered:{route.id}",
                "route_offered",
                "/driver",
                route.offered_at or route.updated_at,
                badge_count=stop_count,
                stops=stop_count,
                distance_km=str(route.planned_distance_km),
            )
        )

    active = (
        DeliveryRoute.objects.filter(driver=driver, status=DeliveryRoute.Status.ACTIVE)
        .prefetch_related("stops")
        .order_by("-created_at")
        .first()
    )
    if active is not None:
        remaining = sum(1 for stop in active.stops.all() if stop.status not in TERMINAL_STOP_STATES)
        items.append(
            _item(
                # plan_version bumps whenever the remaining stops are re-optimised,
                # so the driver is told when their route changed under them.
                f"route:{active.id}:{active.plan_version}",
                "route_active",
                "/driver",
                active.started_at or active.accepted_at or active.updated_at,
                badge_count=remaining,
                stops=remaining,
            )
        )

    failed_stops = RouteStop.objects.filter(
        route__driver=driver,
        status=RouteStop.Status.FAILED,
        updated_at__gte=timezone.now() - timedelta(days=RECENT_DAYS),
    ).order_by("-updated_at")[:MAX_ITEMS]
    for stop in failed_stops:
        items.append(
            _item(
                f"route-stop-failed:{stop.id}",
                "route_stop_failed",
                "/driver",
                stop.updated_at,
                label=stop.label,
            )
        )
    return items


def _admin_feed(user) -> list[dict]:
    now = timezone.now()
    items: list[dict] = []

    applications = PharmacyApplication.objects.filter(status=PharmacyApplication.Status.PENDING).order_by("-created_at")
    for application in applications[:MAX_ITEMS]:
        items.append(
            _item(
                f"application:{application.id}",
                "application",
                "/admin/pharmacy-applications",
                application.created_at,
                pharmacy_name=application.pharmacy_name,
                area=application.area or application.city or None,
            )
        )

    awaiting = (
        Order.objects.filter(
            status__in=[Order.Status.CONFIRMED, Order.Status.READY],
            fulfillment_type=Order.FulfillmentType.DELIVERY,
        )
        .exclude(route_stops__isnull=False)
        .distinct()
        .count()
    )
    if awaiting:
        items.append(
            _item(
                f"dispatch-awaiting:{timezone.localdate().isoformat()}",
                "dispatch",
                "/admin/dispatch",
                now,
                badge_count=awaiting,
                count=awaiting,
            )
        )

    needs_redispatch = OrderFulfillment.objects.filter(status=OrderFulfillment.Status.DELIVERY_FAILED).count()
    if needs_redispatch:
        items.append(
            _item(
                f"dispatch-exceptions:{timezone.localdate().isoformat()}",
                "dispatch_exception",
                "/admin/dispatch",
                now,
                badge_count=needs_redispatch,
                count=needs_redispatch,
            )
        )

    claims = InsuranceClaim.objects.filter(status=InsuranceClaim.Status.SUBMITTED).select_related("policy").order_by("-created_at")[:MAX_ITEMS]
    for claim in claims:
        items.append(
            _item(
                f"admin-insurance-claim:{claim.id}",
                "insurance_claim",
                "/admin/insurance",
                claim.created_at,
                status_label=claim.get_status_display(),
                holder_name=claim.policy.holder_name,
            )
        )

    billing_items = PharmacySubscription.objects.filter(status=PharmacySubscription.Status.PAST_DUE).order_by("-updated_at")[:MAX_ITEMS]
    for subscription in billing_items:
        items.append(
            _item(
                f"admin-billing:{subscription.id}:{subscription.status}",
                "billing_attention",
                "/admin/billing",
                subscription.updated_at,
                count=1,
            )
        )

    failed_imports = InventoryImport.objects.filter(status=InventoryImport.Status.FAILED).order_by("-updated_at")[:MAX_ITEMS]
    for inventory_import in failed_imports:
        items.append(
            _item(
                f"admin-import-failed:{inventory_import.id}",
                "import_failed",
                "/admin/imports",
                inventory_import.updated_at,
                filename=inventory_import.original_filename,
            )
        )
    return items
