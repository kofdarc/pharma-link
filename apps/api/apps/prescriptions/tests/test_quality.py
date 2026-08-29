import io

from django.test import SimpleTestCase

from apps.prescriptions.services.quality import blocking, check_scan_bytes, rejection_message, warnings


def _png(image):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _codes(findings):
    return {f["code"] for f in findings}


class ScanQualityTests(SimpleTestCase):
    def test_pdf_and_empty_payloads_are_never_inspected(self):
        self.assertEqual(check_scan_bytes(b"", mime_type="image/png"), [])
        self.assertEqual(check_scan_bytes(b"%PDF-1.4", mime_type="application/pdf"), [])

    def test_blank_frame_is_flagged_as_no_writing(self):
        from PIL import Image

        findings = check_scan_bytes(_png(Image.new("RGB", (1000, 1400), (205, 205, 205))), mime_type="image/png")
        self.assertIn("no_text", _codes(findings))
        # Advisory, not a refusal.
        self.assertIsNone(rejection_message(findings))
        self.assertIn(
            "We couldn't see any writing in this photo. Make sure the whole prescription is in frame, "
            "filling most of it, and in focus.",
            warnings(findings),
        )

    def test_page_of_text_is_not_flagged_as_no_writing(self):
        from PIL import Image, ImageDraw

        image = Image.new("RGB", (1000, 1400), (232, 230, 224))
        draw = ImageDraw.Draw(image)
        for row in range(20):
            draw.text((60, 60 + row * 60), "Amoxicillin 500 mg  1 cap x3/day  #21  -  Dr Haddad", fill=(10, 10, 10))
        findings = check_scan_bytes(_png(image), mime_type="image/png")
        self.assertNotIn("no_text", _codes(findings))

    def test_too_dark_frame_blocks_and_suppresses_the_writing_check(self):
        from PIL import Image

        findings = check_scan_bytes(_png(Image.new("RGB", (1000, 1400), (12, 12, 12))), mime_type="image/png")
        self.assertEqual(_codes(blocking(findings)), {"too_dark"})
        self.assertNotIn("no_text", _codes(findings))

    def test_tiny_image_blocks(self):
        from PIL import Image

        findings = check_scan_bytes(_png(Image.new("RGB", (200, 150), (200, 200, 200))), mime_type="image/png")
        self.assertIn("too_small", _codes(blocking(findings)))
