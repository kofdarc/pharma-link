from django.conf import settings
from django.core.files.storage import FileSystemStorage

if settings.USE_S3:
    from storages.backends.s3 import S3Storage as _ProductImageBaseStorage
else:
    _ProductImageBaseStorage = FileSystemStorage


class ProductImageStorage(_ProductImageBaseStorage):
    """
    Medicine/supplement photography - unlike prescriptions, this is public, non-sensitive
    catalog data, so it is kept out of the encrypted prescription storage entirely (see
    apps/prescriptions/storage.py) and served from its own root/URL (or S3 prefix) so it can
    be exposed to shoppers directly. See docs/DEPLOY_AWS.md for the bucket policy this prefix
    needs in production.
    """

    def __init__(self, **kwargs):
        if settings.USE_S3:
            kwargs.setdefault("location", "product-images")
        else:
            kwargs.setdefault("location", str(settings.PUBLIC_MEDIA_ROOT))
            remote_base_url = settings.PRODUCT_IMAGE_BASE_URL if settings.DEBUG else ""
            kwargs.setdefault("base_url", remote_base_url or settings.PUBLIC_MEDIA_URL)
        super().__init__(**kwargs)
