from __future__ import annotations

import hashlib
import hmac
import secrets

from django.core import signing

# Ambiguous characters (0/O, 1/I, etc.) are excluded so a pharmacist can read a code off a printout.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
DISPENSE_TICKET_SALT = "pharmalink.eprescriptions.dispense-ticket"
DISPENSE_TICKET_MAX_AGE_SECONDS = 15 * 60


def generate_code() -> str:
    """Human-typeable prescription code, e.g. RX-7F3K-92QD (~10^12 space, and useless without the key/PIN)."""
    part = lambda: "".join(secrets.choice(CODE_ALPHABET) for _ in range(4))  # noqa: E731
    return f"RX-{part()}-{part()}"


def generate_secret() -> str:
    """High-entropy key embedded in the QR link. Never stored in clear."""
    return secrets.token_urlsafe(32)


def generate_pin() -> str:
    """Six digits, for the manual-entry path when a camera is unavailable."""
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_value(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def verify_hash(value: str, expected_hash: str) -> bool:
    if not value or not expected_hash:
        return False
    return hmac.compare_digest(hash_value(value), expected_hash)


def issue_dispense_ticket(prescription_id, *, method: str) -> str:
    """
    Short-lived proof that the caller already authenticated with the QR key or the PIN.
    Lets the dispense request omit the long-lived secret entirely.
    """
    return signing.dumps({"prescription_id": str(prescription_id), "method": method}, salt=DISPENSE_TICKET_SALT)


def read_dispense_ticket(ticket: str) -> dict:
    return signing.loads(ticket, salt=DISPENSE_TICKET_SALT, max_age=DISPENSE_TICKET_MAX_AGE_SECONDS)
