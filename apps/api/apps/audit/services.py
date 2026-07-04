from __future__ import annotations

from typing import Any

from apps.audit.models import AuditLog


def write_audit_log(
    *,
    actor_user=None,
    pharmacy=None,
    action: str,
    entity_type: str,
    entity_id: str,
    summary: str,
    before_data: dict[str, Any] | None = None,
    after_data: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    return AuditLog.objects.create(
        actor_user=actor_user if getattr(actor_user, "is_authenticated", False) else None,
        pharmacy=pharmacy,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        summary=summary,
        before_data=before_data,
        after_data=after_data,
        ip_address=ip_address,
    )

