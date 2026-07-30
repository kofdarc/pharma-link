"""
Machine authentication for the integration bridge.

A pharmacy's software signs each request instead of holding a session:

    canonical = "{method}\\n{path}\\n{timestamp}\\n{nonce}\\n{sha256(body)}"
    signature = hex(hmac_sha256(secret, canonical))

    X-MediSync-Key:       key id
    X-MediSync-Timestamp: unix seconds
    X-MediSync-Nonce:     unique per request
    X-MediSync-Signature: the signature

Why signing rather than a bearer token: the secret never travels, the method/path/body are
bound into the signature so a captured request cannot be re-pointed at another endpoint,
and the timestamp + nonce pair makes replay useless. The secret is stored only as a hash,
so a database compromise cannot be used to forge calls.
"""

from __future__ import annotations

import hashlib
import hmac
import time

from django.db import IntegrityError
from django.utils import timezone
from rest_framework import authentication, exceptions

from apps.integrations.models import IntegrationKey, RequestNonce

MAX_CLOCK_SKEW_SECONDS = 300
SIGNATURE_VERSION_HEADER = "HTTP_X_MEDISYNC_SIGNATURE"


class IntegrationIdentity:
    """Stands in for a user on integration requests, without being one."""

    is_authenticated = True

    def __init__(self, key: IntegrationKey):
        self.integration_key = key
        self.pharmacy = key.pharmacy
        self.pharmacy_id = key.pharmacy_id

    def __str__(self) -> str:
        return f"integration:{self.integration_key.key_id}"


def canonical_string(*, method: str, path: str, timestamp: str, nonce: str, body: bytes) -> str:
    body_hash = hashlib.sha256(body or b"").hexdigest()
    return "\n".join([method.upper(), path, str(timestamp), nonce, body_hash])


def sign(secret: str, canonical: str) -> str:
    return hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()


def fingerprint(secret: str) -> str:
    """Short, non-reversible identifier so a key can be discussed without being exposed."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()[:16]


class IntegrationKeyAuthentication(authentication.BaseAuthentication):
    def authenticate_header(self, request) -> str:
        """
        Without this, DRF reports failed credentials as 403 instead of 401. Connectors
        distinguish the two: 401 means "your credentials are wrong, stop retrying",
        403 means "authenticated but this key lacks the scope".
        """
        return 'MediSync-HMAC-SHA256 realm="api"'

    def authenticate(self, request):
        key_id = request.META.get("HTTP_X_MEDISYNC_KEY")
        if not key_id:
            return None

        timestamp = request.META.get("HTTP_X_MEDISYNC_TIMESTAMP", "")
        nonce = request.META.get("HTTP_X_MEDISYNC_NONCE", "")
        signature = request.META.get(SIGNATURE_VERSION_HEADER, "")
        if not all([timestamp, nonce, signature]):
            raise exceptions.AuthenticationFailed("Signed requests need key, timestamp, nonce and signature headers.")

        try:
            skew = abs(time.time() - float(timestamp))
        except (TypeError, ValueError):
            raise exceptions.AuthenticationFailed("Invalid timestamp.")
        if skew > MAX_CLOCK_SKEW_SECONDS:
            raise exceptions.AuthenticationFailed("Request timestamp is outside the accepted window.")

        key = IntegrationKey.objects.filter(key_id=key_id, is_active=True).select_related("pharmacy").first()
        if key is None or not key.pharmacy.is_active:
            raise exceptions.AuthenticationFailed("Unknown or inactive integration key.")

        canonical = canonical_string(
            method=request.method,
            path=request.path,
            timestamp=timestamp,
            nonce=nonce,
            body=request.body,
        )
        expected = _expected_signature(key, canonical)
        if expected is None or not hmac.compare_digest(expected, signature):
            raise exceptions.AuthenticationFailed("Signature does not match.")

        try:
            RequestNonce.objects.create(integration_key=key, nonce=nonce[:80])
        except IntegrityError:
            raise exceptions.AuthenticationFailed("This request was already processed.")

        key.last_used_at = timezone.now()
        key.last_used_ip = request.META.get("REMOTE_ADDR")
        key.request_count += 1
        key.save(update_fields=["last_used_at", "last_used_ip", "request_count", "updated_at"])
        return IntegrationIdentity(key), key


def _expected_signature(key: IntegrationKey, canonical: str) -> str | None:
    from apps.integrations.services.keys import decrypt_secret

    secret = decrypt_secret(key.secret_encrypted)
    if secret is None:
        return None
    return sign(secret, canonical)
