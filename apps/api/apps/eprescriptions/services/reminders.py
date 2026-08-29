from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from apps.eprescriptions.models import Prescription
from apps.messaging.models import WhatsAppNotification
from apps.messaging.notifications import notify_prescription_expiry


def send_prescription_expiry_reminders(*, now=None) -> int:
    """Send at most a seven-day and a one-day reminder for each live prescription."""
    now = now or timezone.now()
    prescriptions = Prescription.objects.filter(
        status__in=[Prescription.Status.ISSUED, Prescription.Status.PARTIALLY_DISPENSED],
        valid_until__gt=now,
        valid_until__lte=now + timedelta(days=7),
    ).select_related("doctor")
    sent = 0
    for prescription in prescriptions:
        milestone_days = 1 if prescription.valid_until <= now + timedelta(days=1) else 7
        deduplication_key = f"prescription:{prescription.id}:expiry:{milestone_days}d"
        if WhatsAppNotification.objects.filter(deduplication_key=deduplication_key).exists():
            continue
        if notify_prescription_expiry(prescription=prescription, milestone_days=milestone_days) is not None:
            sent += 1
    return sent
