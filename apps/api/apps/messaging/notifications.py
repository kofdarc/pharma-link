from __future__ import annotations

import logging
from collections.abc import Sequence

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import NotificationPreferences, UserRole
from apps.messaging.models import WhatsAppNotification
from apps.messaging.phone import InvalidPhoneNumber, normalize_to_e164
from apps.messaging.providers.registry import get_provider

logger = logging.getLogger(__name__)


def deliver_notification(notification_id) -> WhatsAppNotification:
    notification = WhatsAppNotification.objects.get(id=notification_id)
    if notification.status != WhatsAppNotification.Status.QUEUED:
        return notification
    provider = get_provider(settings.WHATSAPP_PROVIDER)
    result = provider.send_template(
        to=notification.recipient_phone,
        template_name=notification.template_name,
        language_code=notification.language_code,
        body_parameters=[str(value) for value in notification.body_parameters],
        button_url_suffix=notification.button_url_suffix,
    )
    notification.status = result.status
    notification.provider_message_id = result.provider_message_id
    notification.failure_reason = result.failure_reason
    notification.save(update_fields=["status", "provider_message_id", "failure_reason", "updated_at"])
    return notification


def _deliver_safely(notification_id) -> WhatsAppNotification:
    try:
        return deliver_notification(notification_id)
    except Exception as exc:
        logger.exception("WhatsApp notification delivery failed unexpectedly for %s", notification_id)
        notification = WhatsAppNotification.objects.get(id=notification_id)
        notification.status = WhatsAppNotification.Status.FAILED
        notification.failure_reason = str(exc)[:255]
        notification.save(update_fields=["status", "failure_reason", "updated_at"])
        return notification


def enqueue_notification(
    *,
    kind: str,
    deduplication_key: str,
    to: str,
    template_name: str,
    body_parameters: Sequence[str],
    fallback_body: str,
    button_url_suffix: str = "",
    immediate: bool = False,
) -> WhatsAppNotification | None:
    if not to:
        return None
    try:
        normalized = normalize_to_e164(to)
    except InvalidPhoneNumber:
        logger.warning("Skipping %s WhatsApp notification: invalid recipient phone", kind)
        return None
    notification, created = WhatsAppNotification.objects.get_or_create(
        deduplication_key=deduplication_key,
        defaults={
            "kind": kind,
            "recipient_phone": normalized,
            "template_name": template_name,
            "language_code": settings.WHATSAPP_TEMPLATE_LANGUAGE,
            "body_parameters": [str(value) for value in body_parameters],
            "button_url_suffix": button_url_suffix,
            "fallback_body": fallback_body,
        },
    )
    if not created:
        return notification
    if immediate:
        return _deliver_safely(notification.id)
    transaction.on_commit(lambda: _deliver_safely(notification.id), robust=True)
    return notification


def _customer_allows(user, preference: str) -> bool:
    return bool(user and getattr(NotificationPreferences.for_user(user), preference))


def _prescription_customer(prescription):
    if not prescription.patient_email:
        return None
    return (
        get_user_model()
        .objects.filter(email__iexact=prescription.patient_email, role=UserRole.CUSTOMER, is_active=True)
        .first()
    )


def notify_order_update(*, order, event: str, detail: str, pharmacy=None) -> WhatsAppNotification | None:
    if not _customer_allows(order.customer, "order_updates"):
        return None
    pharmacy_key = str(pharmacy.id) if pharmacy else "order"
    return enqueue_notification(
        kind=WhatsAppNotification.Kind.ORDER_UPDATE,
        deduplication_key=f"order:{order.id}:{pharmacy_key}:{event}",
        to=order.contact_phone,
        template_name=settings.WHATSAPP_TEMPLATE_ORDER_STATUS,
        body_parameters=[order.reference, detail],
        fallback_body=f"Order {order.reference}: {detail}",
        button_url_suffix=f"orders/{order.id}",
    )


def notify_pharmacy_new_order(*, fulfillment) -> WhatsAppNotification | None:
    pharmacy = fulfillment.pharmacy
    return enqueue_notification(
        kind=WhatsAppNotification.Kind.PHARMACY_ALERT,
        deduplication_key=f"pharmacy:{pharmacy.id}:order:{fulfillment.id}:new",
        to=pharmacy.whatsapp,
        template_name=settings.WHATSAPP_TEMPLATE_PHARMACY_ALERT,
        body_parameters=["New order", fulfillment.order.reference],
        fallback_body=f"New order {fulfillment.order.reference} requires review in Pharma Link.",
        button_url_suffix="pharmacy/orders",
    )


def notify_pharmacy_new_prescription(*, prescription) -> WhatsAppNotification | None:
    pharmacy = prescription.target_pharmacy
    if pharmacy is None:
        return None
    return enqueue_notification(
        kind=WhatsAppNotification.Kind.PHARMACY_ALERT,
        deduplication_key=f"pharmacy:{pharmacy.id}:prescription:{prescription.id}:new",
        to=pharmacy.whatsapp,
        template_name=settings.WHATSAPP_TEMPLATE_PHARMACY_ALERT,
        body_parameters=["New prescription", prescription.code],
        fallback_body=f"Prescription {prescription.code} requires review in Pharma Link.",
        button_url_suffix="pharmacy/incoming-prescriptions",
    )


def notify_refill(*, recurring, milestone: str, detail: str, occurrence_key: str) -> WhatsAppNotification | None:
    if not _customer_allows(recurring.customer, "refill_reminders"):
        return None
    return enqueue_notification(
        kind=WhatsAppNotification.Kind.REFILL_REMINDER,
        deduplication_key=f"refill:{recurring.id}:{milestone}:{occurrence_key}",
        to=recurring.address.phone,
        template_name=settings.WHATSAPP_TEMPLATE_REFILL_REMINDER,
        body_parameters=[recurring.label, detail],
        fallback_body=f"Refill '{recurring.label}': {detail}",
        button_url_suffix="refills",
    )


def notify_prescription_expiry(*, prescription, milestone_days: int) -> WhatsAppNotification | None:
    customer = _prescription_customer(prescription)
    if not _customer_allows(customer, "prescription_reminders"):
        return None
    phone = prescription.patient_phone or customer.phone
    expiry = timezone.localtime(prescription.valid_until).strftime("%d %b %Y")
    return enqueue_notification(
        kind=WhatsAppNotification.Kind.PRESCRIPTION_EXPIRY,
        deduplication_key=f"prescription:{prescription.id}:expiry:{milestone_days}d",
        to=phone,
        template_name=settings.WHATSAPP_TEMPLATE_PRESCRIPTION_EXPIRY,
        body_parameters=[prescription.code, expiry],
        fallback_body=f"Prescription {prescription.code} expires on {expiry}. Review it securely in Pharma Link.",
        button_url_suffix=f"prescriptions/{prescription.id}",
    )


def notify_renewal_decision(*, renewal_request) -> WhatsAppNotification | None:
    prescription = renewal_request.prescription
    customer = _prescription_customer(prescription)
    if not _customer_allows(customer, "prescription_reminders"):
        return None
    phone = prescription.patient_phone or customer.phone
    detail = "approved" if renewal_request.status == renewal_request.Status.APPROVED else "requires your attention"
    return enqueue_notification(
        kind=WhatsAppNotification.Kind.RENEWAL_DECISION,
        deduplication_key=f"renewal:{renewal_request.id}:{renewal_request.status.lower()}",
        to=phone,
        template_name=settings.WHATSAPP_TEMPLATE_RENEWAL_DECISION,
        body_parameters=[prescription.code, detail],
        fallback_body=f"The renewal request for prescription {prescription.code} was reviewed and {detail}.",
        button_url_suffix=f"prescriptions/{prescription.id}",
    )


def notify_payment_failure(*, payment) -> WhatsAppNotification | None:
    order = payment.order
    if not _customer_allows(order.customer, "order_updates"):
        return None
    return enqueue_notification(
        kind=WhatsAppNotification.Kind.PAYMENT_FAILURE,
        deduplication_key=f"payment:{payment.id}:failed:{timezone.now().isoformat()}",
        to=order.contact_phone,
        template_name=settings.WHATSAPP_TEMPLATE_PAYMENT_FAILED,
        body_parameters=[order.reference],
        fallback_body=f"Payment for order {order.reference} was unsuccessful. Review it securely in Pharma Link.",
        button_url_suffix=f"orders/{order.id}",
        # An initial online charge failure intentionally rolls the new order back. Deliver
        # before that rollback, just as the existing email path does; the external message
        # remains useful even though its local audit row is discarded with the failed order.
        immediate=True,
    )
