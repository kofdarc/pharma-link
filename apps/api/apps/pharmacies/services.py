from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import UserRole
from apps.accounts.services import send_password_reset_email
from apps.orders.models import Order, OrderFulfillment
from apps.orders.services.lifecycle import reject_fulfillment
from apps.payments.models import Payment
from apps.payments.services import refund_payment
from apps.pharmacies.models import Pharmacy, PharmacyApplication

OPEN_FULFILLMENT_STATES = {OrderFulfillment.Status.PENDING, OrderFulfillment.Status.ACCEPTED, OrderFulfillment.Status.READY}


class ApplicationError(Exception):
    pass


@transaction.atomic
def approve_application(*, application: PharmacyApplication, reviewer, note: str = "") -> PharmacyApplication:
    from apps.accounts.models import User

    if application.status != PharmacyApplication.Status.PENDING:
        raise ApplicationError("This application was already reviewed.")
    if User.objects.filter(email__iexact=application.email).exists():
        raise ApplicationError(f"An account already exists for {application.email}.")

    pharmacy = Pharmacy.objects.create(
        name=application.pharmacy_name,
        license_number=application.license_number,
        city=application.city,
        area=application.area,
        phone=application.phone,
        email=application.email,
    )
    owner = User.objects.create_user(
        email=application.email,
        password=None,  # set_password(None) leaves it unusable until the reset link below is used
        role=UserRole.PHARMACY_OWNER,
        pharmacy=pharmacy,
        first_name=application.owner_name,
        email_verified=True,
    )
    send_password_reset_email(owner)  # doubles as "set your initial password"

    application.status = PharmacyApplication.Status.APPROVED
    application.review_note = note
    application.reviewed_at = timezone.now()
    application.reviewed_by = reviewer
    application.created_pharmacy = pharmacy
    application.save(update_fields=["status", "review_note", "reviewed_at", "reviewed_by", "created_pharmacy", "updated_at"])
    return application


def reject_application(*, application: PharmacyApplication, reviewer, note: str = "") -> PharmacyApplication:
    if application.status != PharmacyApplication.Status.PENDING:
        raise ApplicationError("This application was already reviewed.")
    application.status = PharmacyApplication.Status.REJECTED
    application.review_note = note
    application.reviewed_at = timezone.now()
    application.reviewed_by = reviewer
    application.save(update_fields=["status", "review_note", "reviewed_at", "reviewed_by", "updated_at"])
    return application


def deactivate_pharmacy(*, pharmacy, user=None) -> None:
    """
    Closing a pharmacy must not strand its open order slices: each is rejected (releasing any
    held stock, waiving any service fee already charged - see reject_fulfillment) so a
    shopper isn't left waiting on a pharmacy that can no longer act. If that empties an order
    entirely, the order lands on CANCELLED via the usual rollup, and its payment is refunded
    the same way a full shopper-initiated cancellation would be.
    """
    affected_order_ids = set()
    for fulfillment in OrderFulfillment.objects.filter(pharmacy=pharmacy, status__in=OPEN_FULFILLMENT_STATES):
        affected_order_ids.add(fulfillment.order_id)
        reject_fulfillment(fulfillment=fulfillment, user=user, reason="Pharmacy deactivated")

    for order in Order.objects.filter(id__in=affected_order_ids, status=Order.Status.CANCELLED).select_related("payment"):
        payment = getattr(order, "payment", None)
        if payment is not None and payment.status == Payment.Status.PAID:
            refund_payment(payment=payment, user=user)
