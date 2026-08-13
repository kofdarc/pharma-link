from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet
from django.conf import settings


def fernet_for(purpose: str) -> Fernet:
    """
    A Fernet key derived from DJANGO_SECRET_KEY, distinct per `purpose` so different
    subsystems don't share a key even though both ultimately trace back to the same
    Django secret. Same POC-appropriate tradeoff apps.integrations.services.keys already
    documents for integration secrets: in production this should be its own rotated
    secret (or a KMS-held key) per purpose, not derived from SECRET_KEY.
    """
    digest = hashlib.sha256(f"{purpose}:{settings.SECRET_KEY}".encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))
