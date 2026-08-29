from __future__ import annotations

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.audit.services import write_audit_log
from apps.messaging.models import Conversation, Message, WhatsAppNotification
from apps.messaging.phone import InvalidPhoneNumber, normalize_to_e164
from apps.messaging.providers.base import SendResult
from apps.messaging.providers.registry import get_provider


def send_whatsapp_text(*, to: str, body: str) -> SendResult:
    """
    The one chokepoint every WhatsApp send in the codebase goes through - mirrors
    apps.common.mailer.send_email. Used by both chat message delivery (below) and refill
    reminders (apps.orders.services.schedule). A malformed number is reported back as a
    FAILED SendResult rather than raised, so a bad number behaves like any other delivery
    failure instead of a 500 or a broken transaction.
    """
    try:
        normalized = normalize_to_e164(to)
    except InvalidPhoneNumber as exc:
        return SendResult(status=Message.Status.FAILED, failure_reason=str(exc)[:255])
    provider = get_provider(settings.WHATSAPP_PROVIDER)
    return provider.send_text(to=normalized, body=body)


def get_or_create_conversation(*, order_fulfillment=None, prescription=None) -> Conversation:
    if order_fulfillment is not None:
        conversation, _created = Conversation.objects.get_or_create(
            order_fulfillment=order_fulfillment,
            defaults={
                "customer": order_fulfillment.order.customer,
                "pharmacy": order_fulfillment.pharmacy,
                "customer_phone": order_fulfillment.order.contact_phone,
            },
        )
        return conversation
    if prescription is not None:
        if not prescription.target_pharmacy_id:
            raise ValueError("This prescription has no target pharmacy to message.")
        conversation, _created = Conversation.objects.get_or_create(
            prescription=prescription,
            defaults={
                "doctor_user": prescription.doctor.user,
                "pharmacy": prescription.target_pharmacy,
                "customer_phone": prescription.doctor.phone,
            },
        )
        return conversation
    raise ValueError("Provide order_fulfillment or prescription.")


def _recipient_phone(conversation: Conversation, sender) -> str:
    """
    Every outbound send picks up the phone WhatsApp delivery. On an order conversation the
    pharmacy is always the in-app sender, so it's unambiguous: notify the shopper on
    customer_phone. A prescription conversation has two in-app senders (doctor, pharmacy), so
    whichever one *didn't* send needs to be the recipient - a pharmacy-staff sender notifies
    the doctor's phone (customer_phone), anyone else (the doctor, or a system message like a
    cancellation notice) notifies the pharmacy's WhatsApp number instead.
    """
    if conversation.prescription_id and not (sender is not None and getattr(sender, "pharmacy_id", None) == conversation.pharmacy_id):
        return conversation.pharmacy.whatsapp
    return conversation.customer_phone


@transaction.atomic
def send_message(*, conversation: Conversation, sender, body: str, recipient_phone: str | None = None) -> Message:
    """
    Persists the message, sends it, and records the outcome - mirrors how
    apps.payments.services.charge_payment locks, delegates, and writes an audit log.
    `recipient_phone` overrides the sender-based inference in `_recipient_phone` - needed for
    system messages (sender=None) where who should be notified isn't the sender's counterpart
    (e.g. a dispense-time substitution notice always goes to the doctor, never the pharmacy
    that just performed the substitution, even though both are "system" sends).
    """
    message = Message.objects.create(conversation=conversation, sender_user=sender, direction=Message.Direction.OUTBOUND, body=body, status=Message.Status.QUEUED)
    result = send_whatsapp_text(to=recipient_phone or _recipient_phone(conversation, sender), body=body)
    message.status = result.status
    message.provider_message_id = result.provider_message_id
    message.failure_reason = result.failure_reason
    message.save(update_fields=["status", "provider_message_id", "failure_reason", "updated_at"])
    conversation.last_message_at = timezone.now()
    conversation.save(update_fields=["last_message_at", "updated_at"])
    write_audit_log(
        actor_user=sender,
        pharmacy=conversation.pharmacy,
        action="messaging.sent" if result.status != Message.Status.FAILED else "messaging.send_failed",
        entity_type="Message",
        entity_id=message.id,
        summary=f"WhatsApp message on {conversation.order_fulfillment or conversation.prescription}: {message.status}",
    )
    return message


def _same_number(a: str, b: str) -> bool:
    try:
        return normalize_to_e164(a) == b
    except Exception:
        return False


def ingest_inbound(*, from_phone: str, to_phone: str, body: str) -> Message | None:
    """
    Matches an inbound WhatsApp reply to an existing Conversation. Matching on the shopper's
    phone alone is not enough - the same shopper can have concurrent conversations with two
    different pharmacies - so this also matches the pharmacy's WhatsApp number (the webhook's
    recipient) against Pharmacy.whatsapp. Returns None (and stores nothing) if no conversation
    matches, since there is nowhere safe to file an unsolicited inbound message.
    """
    try:
        normalized_from = normalize_to_e164(from_phone)
        normalized_to = normalize_to_e164(to_phone)
    except Exception:
        return None
    candidates = Conversation.objects.filter(customer_phone=normalized_from).select_related("pharmacy").order_by("-last_message_at")
    conversation = next((candidate for candidate in candidates if _same_number(candidate.pharmacy.whatsapp, normalized_to)), None)
    if conversation is None:
        return None
    message = Message.objects.create(conversation=conversation, sender_user=None, direction=Message.Direction.INBOUND, body=body, status=Message.Status.RECEIVED)
    conversation.last_message_at = timezone.now()
    conversation.save(update_fields=["last_message_at", "updated_at"])
    return message


def ingest_delivery_status(*, provider_message_id: str, provider_status: str, failure_reason: str = "") -> bool:
    status_map = {
        "sent": Message.Status.SENT,
        "delivered": Message.Status.DELIVERED,
        "read": Message.Status.READ,
        "failed": Message.Status.FAILED,
    }
    mapped = status_map.get(provider_status.lower())
    if not provider_message_id or mapped is None:
        return False
    message = Message.objects.filter(provider_message_id=provider_message_id).first()
    if message is not None:
        message.status = mapped
        message.failure_reason = failure_reason[:255]
        message.save(update_fields=["status", "failure_reason", "updated_at"])
        return True
    notification = WhatsAppNotification.objects.filter(provider_message_id=provider_message_id).first()
    if notification is None:
        return False
    notification.status = mapped
    notification.failure_reason = failure_reason[:255]
    notification.save(update_fields=["status", "failure_reason", "updated_at"])
    return True
