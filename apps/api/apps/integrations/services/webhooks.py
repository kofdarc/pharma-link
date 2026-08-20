"""
Outgoing webhooks: push platform events to a pharmacy's own software instead of it polling.

dispatch_webhook_event() only ever writes a WebhookDelivery row - it must stay fast and do
no network I/O, since it is called from inside request/transaction paths like order
placement. The actual signed HTTP POST happens later, in deliver_pending_webhooks(), which
the polling `run_scheduler` management command calls on every pass. There is no
Celery/task queue in this codebase by design; that polling loop is the only async
mechanism.

Outgoing requests are signed with the same scheme the machine API uses to verify incoming
ones (see apps.integrations.authentication and docs/ARCHITECTURE.md section 6):

    canonical = "{method}\\n{path}\\n{timestamp}\\n{nonce}\\n{sha256(body)}"
    signature = hex(hmac_sha256(secret, canonical))

sent as X-PharmaLink-Timestamp / X-PharmaLink-Nonce / X-PharmaLink-Signature headers, so a
receiver can verify the payload actually came from us and was not tampered with in transit.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
import uuid
from urllib.parse import urlparse

from django.utils import timezone

from apps.integrations.authentication import canonical_string, sign
from apps.integrations.models import WebhookDelivery, WebhookEndpoint

logger = logging.getLogger(__name__)

WEBHOOK_TIMEOUT_SECONDS = 5
MAX_WEBHOOK_ATTEMPTS = 5


def dispatch_webhook_event(*, pharmacy, event_type: str, payload: dict) -> None:
    """
    Fans an event out to every active endpoint subscribed to it, as a PENDING row. Fast and
    write-only: no HTTP call happens here.
    """
    endpoints = WebhookEndpoint.objects.filter(pharmacy=pharmacy, is_active=True)
    for endpoint in endpoints:
        if endpoint.events and event_type not in endpoint.events:
            continue
        WebhookDelivery.objects.create(
            endpoint=endpoint,
            event=event_type,
            payload=payload,
            status=WebhookDelivery.Status.PENDING,
        )


def _deliver_one(delivery: WebhookDelivery) -> bool:
    endpoint = delivery.endpoint
    body = json.dumps({"event": delivery.event, "payload": delivery.payload}, default=str).encode("utf-8")
    path = urlparse(endpoint.url).path or "/"
    timestamp = str(int(time.time()))
    nonce = uuid.uuid4().hex
    canonical = canonical_string(method="POST", path=path, timestamp=timestamp, nonce=nonce, body=body)
    signature = sign(endpoint.secret, canonical)

    request = urllib.request.Request(
        endpoint.url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-PharmaLink-Timestamp": timestamp,
            "X-PharmaLink-Nonce": nonce,
            "X-PharmaLink-Signature": signature,
        },
    )
    status_code = None
    error = ""
    try:
        with urllib.request.urlopen(request, timeout=WEBHOOK_TIMEOUT_SECONDS) as response:
            status_code = response.getcode()
        ok = 200 <= status_code < 300
        if not ok:
            error = f"HTTP {status_code}"
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        ok = False
        error = f"HTTP {exc.code}"
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        ok = False
        error = str(exc)[:255]

    delivery.attempts += 1
    delivery.status_code = status_code
    delivery.error = error
    if ok:
        delivery.status = WebhookDelivery.Status.DELIVERED
        delivery.delivered_at = timezone.now()
        endpoint.consecutive_failures = 0
    else:
        endpoint.consecutive_failures += 1
        if delivery.attempts >= MAX_WEBHOOK_ATTEMPTS:
            delivery.status = WebhookDelivery.Status.FAILED
        # else: left PENDING so the next scheduler pass retries it.
    delivery.save(update_fields=["attempts", "status_code", "error", "status", "delivered_at", "updated_at"])
    endpoint.last_delivery_at = timezone.now()
    endpoint.save(update_fields=["last_delivery_at", "consecutive_failures", "updated_at"])
    return ok


def deliver_pending_webhooks() -> int:
    """
    Called from run_scheduler's polling loop. Attempts every PENDING delivery once and
    returns how many were attempted (delivered, retried, or given up on).
    """
    pending = list(WebhookDelivery.objects.filter(status=WebhookDelivery.Status.PENDING).select_related("endpoint"))
    for delivery in pending:
        try:
            _deliver_one(delivery)
        except Exception:  # noqa: BLE001 - one bad delivery must not stop the pass
            logger.exception("Unexpected error delivering webhook %s", delivery.id)
    return len(pending)
