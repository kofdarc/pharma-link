from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.accounts.models import UserRole
from apps.audit.services import write_audit_log
from apps.eprescriptions.models import Doctor


class ActivationError(Exception):
    pass


@transaction.atomic
def activate_doctor(*, license_number: str, email: str, password: str) -> Doctor:
    """
    Zero-onboarding claim flow. The Order of Physicians roster already holds the doctor's
    identity, so activation only proves control of the registered email + licence pair
    and sets a password. No profile forms, no admin approval.
    """
    doctor = Doctor.objects.select_for_update().filter(license_number__iexact=license_number.strip()).first()
    if doctor is None or doctor.email.lower() != email.strip().lower():
        # Same message either way so the endpoint cannot be used to enumerate the roster.
        raise ActivationError(_("No matching licence and email were found in the Order of Physicians roster."))
    if not doctor.is_active:
        raise ActivationError(_("This licence is not currently active."))
    if doctor.is_activated:
        raise ActivationError(_("This account is already activated. Use the login page or reset your password."))

    try:
        validate_password(password)
    except ValidationError as exc:
        raise ActivationError(" ".join(exc.messages))

    User = get_user_model()
    if User.objects.filter(email__iexact=doctor.email).exists():
        raise ActivationError(_("A user already exists for this email address."))

    names = doctor.full_name.split(" ", 1)
    user = User.objects.create_user(
        email=doctor.email,
        password=password,
        role=UserRole.DOCTOR,
        first_name=names[0],
        last_name=names[1] if len(names) > 1 else "",
        is_active=True,
    )
    doctor.user = user
    doctor.is_activated = True
    doctor.activated_at = timezone.now()
    doctor.save(update_fields=["user", "is_activated", "activated_at", "updated_at"])
    write_audit_log(
        actor_user=user,
        action="eprescriptions.doctor_activated",
        entity_type="Doctor",
        entity_id=doctor.id,
        summary=f"Dr. {doctor.full_name} activated licence {doctor.license_number}",
    )
    return doctor
