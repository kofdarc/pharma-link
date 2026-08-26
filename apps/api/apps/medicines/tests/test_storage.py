from django.test import SimpleTestCase, override_settings

from apps.medicines.storage import ProductImageStorage


class ProductImageStorageTests(SimpleTestCase):
    @override_settings(
        DEBUG=True,
        USE_S3=False,
        PRODUCT_IMAGE_BASE_URL="https://example-bucket.s3.eu-central-1.amazonaws.com/product-images/",
    )
    def test_development_can_read_images_from_remote_base_url(self):
        storage = ProductImageStorage()

        self.assertEqual(
            storage.url("medicines/0010db72-8853-4b45-ba6e-dc81e827f32b.webp"),
            "https://example-bucket.s3.eu-central-1.amazonaws.com/product-images/medicines/0010db72-8853-4b45-ba6e-dc81e827f32b.webp",
        )

    @override_settings(
        DEBUG=False,
        USE_S3=False,
        PRODUCT_IMAGE_BASE_URL="https://example-bucket.s3.eu-central-1.amazonaws.com/product-images/",
        PUBLIC_MEDIA_URL="/media/",
    )
    def test_remote_development_url_is_ignored_outside_debug(self):
        storage = ProductImageStorage()

        self.assertEqual(storage.url("medicines/example.webp"), "/media/medicines/example.webp")
