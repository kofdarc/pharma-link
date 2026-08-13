from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage

from apps.common.crypto import fernet_for

PURPOSE = "prescriptions.file"


class EncryptedPrescriptionStorage(FileSystemStorage):
    """
    Scanned prescriptions are medical records - the most sensitive files this platform
    stores - so they are encrypted before touching disk. Transparent to callers:
    `record.file.open()`/`.read()` returns decrypted bytes, `.save()` encrypts before
    writing. Moving the backend to S3 later only means swapping the base Storage class;
    this wrapper's encrypt/decrypt behaviour does not change.
    """

    def _open(self, name, mode="rb"):
        raw = super()._open(name, mode)
        try:
            decrypted = fernet_for(PURPOSE).decrypt(raw.read())
        finally:
            raw.close()
        return ContentFile(decrypted, name=name)

    def _save(self, name, content):
        encrypted = fernet_for(PURPOSE).encrypt(content.read())
        return super()._save(name, ContentFile(encrypted))
