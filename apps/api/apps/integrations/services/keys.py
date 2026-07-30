from __future__ import annotations

import base64
import hashlib
import secrets

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.utils import timezone

from apps.audit.services import write_audit_log
from apps.integrations.authentication import fingerprint
from apps.integrations.models import IntegrationKey


def _fernet() -> Fernet:
    """
    Encryption key derived from DJANGO_SECRET_KEY so a POC needs no extra key management.
    In production this should be its own rotated secret (or a KMS-held key) so that
    rotating the Django secret does not invalidate every pharmacy's connector.
    """
    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode("utf-8")).decode("utf-8")


def decrypt_secret(token: str) -> str | None:
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return None


def create_integration_key(*, pharmacy, user, name: str = "POS connector", scopes: list[str] | None = None) -> tuple[IntegrationKey, str]:
    """Returns (key, plaintext_secret). The secret is shown once and never again."""
    scopes = scopes or [
        IntegrationKey.Scope.STOCK_WRITE,
        IntegrationKey.Scope.SALES_WRITE,
        IntegrationKey.Scope.ORDERS_READ,
        IntegrationKey.Scope.ORDERS_WRITE,
    ]
    secret = secrets.token_urlsafe(36)
    key = IntegrationKey.objects.create(
        pharmacy=pharmacy,
        name=name,
        key_id=f"msk_{secrets.token_hex(10)}",
        secret_encrypted=encrypt_secret(secret),
        secret_fingerprint=fingerprint(secret),
        scopes=list(scopes),
        created_by=user,
    )
    write_audit_log(
        actor_user=user,
        pharmacy=pharmacy,
        action="integrations.key_created",
        entity_type="IntegrationKey",
        entity_id=key.id,
        summary=f"Created integration key {key.key_id} ({name})",
        after_data={"scopes": key.scopes},
    )
    return key, secret


def revoke_integration_key(*, key: IntegrationKey, user) -> IntegrationKey:
    key.is_active = False
    key.revoked_at = timezone.now()
    key.save(update_fields=["is_active", "revoked_at", "updated_at"])
    write_audit_log(
        actor_user=user,
        pharmacy=key.pharmacy,
        action="integrations.key_revoked",
        entity_type="IntegrationKey",
        entity_id=key.id,
        summary=f"Revoked integration key {key.key_id}",
    )
    return key
