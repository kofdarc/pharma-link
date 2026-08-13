from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.eprescriptions.models import Prescription, PrescriptionAccessLog
from apps.eprescriptions.services import tokens


class PrescriptionAuthError(Exception):
    def __init__(self, message: str, *, status: int = 404):
        super().__init__(message)
        self.status = status


def client_ip(request) -> str | None:
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def log_access(*, prescription=None, code_attempted="", action, method="", request=None, detail=""):
    PrescriptionAccessLog.objects.create(
        prescription=prescription,
        code_attempted=code_attempted[:64],
        action=action,
        method=method,
        ip_address=client_ip(request),
        user_agent=(request.META.get("HTTP_USER_AGENT", "")[:255] if request is not None else ""),
        detail=detail[:255],
    )


def authenticate(*, code: str, key: str = "", pin: str = "", request=None) -> tuple[Prescription, str]:
    """
    Resolves a prescription from the QR key or the manual PIN.

    Deliberate choices:
      - the code alone is never enough, so a guessed or shoulder-surfed code leaks nothing
      - failures are counted per prescription and lock it briefly, which makes PIN brute force useless
      - every attempt is logged, so a doctor and the platform can see who touched a prescription

    NOTE ON TRANSACTIONS: this function must NOT be wrapped in `transaction.atomic`. The
    failure paths raise, and a surrounding atomic block would roll back exactly the writes
    that make the defences work - the access log entry and the failed-attempt counter. So
    the locked read/write happens inside a short atomic block that commits, and the error is
    raised only after that block has closed.
    """
    code = (code or "").strip().upper()
    method = ""
    failure: PrescriptionAuthError | None = None

    with transaction.atomic():
        prescription = Prescription.objects.select_for_update().filter(code=code).first()
        if prescription is None:
            log_access(
                code_attempted=code,
                action=PrescriptionAccessLog.Action.AUTH_FAILED,
                method="QR" if key else "MANUAL",
                request=request,
                detail="Unknown code",
            )
            failure = PrescriptionAuthError("No prescription matches that code.")
        elif prescription.is_locked:
            log_access(prescription=prescription, code_attempted=code, action=PrescriptionAccessLog.Action.LOCKED, request=request, detail="Locked out")
            failure = PrescriptionAuthError("Too many failed attempts. Try again shortly.", status=429)
        else:
            if key and tokens.verify_hash(key, prescription.secret_hash):
                method = "QR"
            elif pin and tokens.verify_hash(pin.strip(), prescription.pin_hash):
                method = "MANUAL"

            if not method:
                prescription.failed_auth_count += 1
                fields = ["failed_auth_count", "updated_at"]
                if prescription.failed_auth_count >= settings.PRESCRIPTION_MAX_FAILED_ATTEMPTS:
                    prescription.locked_until = timezone.now() + timedelta(minutes=settings.PRESCRIPTION_LOCKOUT_MINUTES)
                    prescription.failed_auth_count = 0
                    fields.append("locked_until")
                prescription.save(update_fields=fields)
                log_access(
                    prescription=prescription,
                    code_attempted=code,
                    action=PrescriptionAccessLog.Action.AUTH_FAILED,
                    method="QR" if key else "MANUAL",
                    request=request,
                    detail="Bad key or PIN",
                )
                failure = PrescriptionAuthError("The prescription key or PIN is not valid.", status=403)
            else:
                if prescription.failed_auth_count:
                    prescription.failed_auth_count = 0
                    prescription.save(update_fields=["failed_auth_count", "updated_at"])

                if prescription.status == Prescription.Status.CANCELLED:
                    log_access(prescription=prescription, code_attempted=code, action=PrescriptionAccessLog.Action.VIEW, method=method, request=request, detail="Cancelled")
                    failure = PrescriptionAuthError("This prescription was cancelled by the prescribing doctor.", status=409)
                else:
                    if prescription.is_expired and prescription.status != Prescription.Status.EXPIRED:
                        prescription.status = Prescription.Status.EXPIRED
                        prescription.save(update_fields=["status", "updated_at"])
                    log_access(prescription=prescription, code_attempted=code, action=PrescriptionAccessLog.Action.VIEW, method=method, request=request)

    if failure is not None:
        raise failure
    return prescription, method
