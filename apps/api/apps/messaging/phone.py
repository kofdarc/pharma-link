from __future__ import annotations

import phonenumbers


class InvalidPhoneNumber(ValueError):
    pass


def normalize_to_e164(raw: str, *, default_region: str = "LB") -> str:
    """
    Numbers stored across the platform (DeliveryAddress.phone, Order.contact_phone, ...) have
    no format validation today, so this is the one place that turns whatever a shopper typed
    into a real E.164 number - or raises loudly, rather than letting a malformed number reach
    WhatsApp's API and fail silently there.
    """
    try:
        parsed = phonenumbers.parse(raw, default_region)
    except phonenumbers.NumberParseException as exc:
        raise InvalidPhoneNumber(f"'{raw}' is not a parseable phone number: {exc}") from exc
    if not phonenumbers.is_valid_number(parsed):
        raise InvalidPhoneNumber(f"'{raw}' is not a valid phone number.")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
