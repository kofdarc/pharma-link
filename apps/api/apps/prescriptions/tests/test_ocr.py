"""
OCR provider adapters (apps.prescriptions.services.ocr). See docs/AI_FEATURES.md §2.

TesseractOcrProvider tests exercise the real, self-hosted engine and are skipped if the
`tesseract` binary isn't installed, so this suite stays portable across environments that
haven't installed the system package yet (the production Dockerfile does).

AnthropicOcrProvider tests mock the HTTP call - no network access, no API key needed to run
this suite, and no risk of the tests silently depending on Anthropic's API being reachable.
"""

import importlib.util
import io
import json
import shutil
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from django.test import TestCase, override_settings

from apps.prescriptions.services.ocr.anthropic import AnthropicOcrProvider
from apps.prescriptions.services.ocr.base import OcrProviderError, UnsupportedFileType
from apps.prescriptions.services.ocr.easyocr_provider import EasyOcrProvider
from apps.prescriptions.services.ocr.registry import get_provider
from apps.prescriptions.services.ocr.tesseract import TesseractOcrProvider

TESSERACT_AVAILABLE = shutil.which("tesseract") is not None
POPPLER_AVAILABLE = shutil.which("pdftoppm") is not None
EASYOCR_AVAILABLE = importlib.util.find_spec("easyocr") is not None


def _render_text_image(text: str):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (400, 80), color="white")
    draw = ImageDraw.Draw(image)
    draw.text((10, 25), text, fill="black")
    return image


def _render_text_png(text: str) -> io.BytesIO:
    buffer = io.BytesIO()
    _render_text_image(text).save(buffer, format="PNG")
    buffer.seek(0)
    buffer.name = "scan.png"
    return buffer


def _render_text_pdf(text: str) -> io.BytesIO:
    buffer = io.BytesIO()
    _render_text_image(text).save(buffer, format="PDF")
    buffer.seek(0)
    buffer.name = "scan.pdf"
    return buffer


@unittest.skipUnless(TESSERACT_AVAILABLE, "tesseract binary not installed in this environment")
class TesseractOcrProviderTests(TestCase):
    def test_extracts_text_from_a_printed_image(self):
        image = _render_text_png("PANADOL 500MG")

        result = TesseractOcrProvider().extract_text(image, mime_type="image/png")

        self.assertIn("PANADOL", result.text.upper())
        self.assertEqual(result.provider, "tesseract")

    def test_reports_a_confidence_score_for_a_clean_printed_image(self):
        image = _render_text_png("PANADOL 500MG")

        result = TesseractOcrProvider().extract_text(image, mime_type="image/png")

        self.assertIsNotNone(result.confidence)
        self.assertGreaterEqual(result.confidence, 0)
        self.assertLessEqual(result.confidence, 1)

    def test_rejects_an_unsupported_file_type(self):
        with self.assertRaises(UnsupportedFileType):
            TesseractOcrProvider().extract_text(io.BytesIO(b"not an image"), mime_type="image/gif")

    @unittest.skipUnless(POPPLER_AVAILABLE, "poppler-utils (pdftoppm) not installed in this environment")
    def test_extracts_text_from_a_pdf(self):
        pdf = _render_text_pdf("PANADOL 500MG")

        result = TesseractOcrProvider().extract_text(pdf, mime_type="application/pdf")

        self.assertIn("PANADOL", result.text.upper())
        self.assertEqual(result.provider, "tesseract")

    @unittest.skipUnless(POPPLER_AVAILABLE, "poppler-utils (pdftoppm) not installed in this environment")
    def test_malformed_pdf_raises_a_provider_error_not_a_silent_empty_result(self):
        with self.assertRaises(OcrProviderError):
            TesseractOcrProvider().extract_text(io.BytesIO(b"%PDF-1.4\nnot a real pdf"), mime_type="application/pdf")


class AnthropicOcrProviderTests(TestCase):
    def test_rejects_an_unsupported_file_type(self):
        with self.assertRaises(UnsupportedFileType):
            AnthropicOcrProvider().extract_text(io.BytesIO(b"not an image"), mime_type="image/gif")

    @override_settings(ANTHROPIC_API_KEY="test-key", ANTHROPIC_OCR_MODEL="claude-sonnet-5")
    def test_sends_a_document_block_for_a_pdf(self):
        response_body = json.dumps({"content": [{"type": "text", "text": "Panadol 500mg x30"}]}).encode("utf-8")
        fake_response = MagicMock()
        fake_response.read.return_value = response_body
        fake_response.__enter__.return_value = fake_response
        fake_response.__exit__.return_value = False

        with patch("urllib.request.urlopen", return_value=fake_response) as mock_urlopen:
            result = AnthropicOcrProvider().extract_text(io.BytesIO(b"%PDF-1.4 fake pdf bytes"), mime_type="application/pdf")

        self.assertEqual(result.text, "Panadol 500mg x30")
        request = mock_urlopen.call_args[0][0]
        payload = json.loads(request.data)
        content_block = payload["messages"][0]["content"][0]
        self.assertEqual(content_block["type"], "document")
        self.assertEqual(content_block["source"]["media_type"], "application/pdf")

    @override_settings(ANTHROPIC_API_KEY="test-key", ANTHROPIC_OCR_MODEL="claude-sonnet-5")
    def test_successful_transcription(self):
        response_body = json.dumps({"content": [{"type": "text", "text": "Panadol 500mg x30"}]}).encode("utf-8")
        fake_response = MagicMock()
        fake_response.read.return_value = response_body
        fake_response.__enter__.return_value = fake_response
        fake_response.__exit__.return_value = False

        with patch("urllib.request.urlopen", return_value=fake_response) as mock_urlopen:
            result = AnthropicOcrProvider().extract_text(io.BytesIO(b"fake-image-bytes"), mime_type="image/jpeg")

        self.assertEqual(result.text, "Panadol 500mg x30")
        self.assertEqual(result.provider, "anthropic")
        request = mock_urlopen.call_args[0][0]
        self.assertEqual(request.get_header("X-api-key"), "test-key")

    @override_settings(ANTHROPIC_API_KEY="test-key", ANTHROPIC_OCR_MODEL="claude-sonnet-5")
    def test_requests_adaptive_thinking_for_handwriting(self):
        response_body = json.dumps({"content": [{"type": "text", "text": "x"}]}).encode("utf-8")
        fake_response = MagicMock()
        fake_response.read.return_value = response_body
        fake_response.__enter__.return_value = fake_response
        fake_response.__exit__.return_value = False

        with patch("urllib.request.urlopen", return_value=fake_response) as mock_urlopen:
            AnthropicOcrProvider().extract_text(io.BytesIO(b"fake-image-bytes"), mime_type="image/jpeg")

        payload = json.loads(mock_urlopen.call_args[0][0].data)
        self.assertEqual(payload["thinking"], {"type": "adaptive"})
        self.assertEqual(payload["output_config"], {"effort": "high"})
        self.assertGreater(payload["max_tokens"], 1024)

    @override_settings(ANTHROPIC_API_KEY="test-key", ANTHROPIC_OCR_MODEL="claude-sonnet-5")
    def test_thinking_blocks_are_dropped_from_the_transcription(self):
        response_body = json.dumps(
            {
                "content": [
                    {"type": "thinking", "thinking": "the second stroke reads like an 'l'..."},
                    {"type": "text", "text": "Amoxicilline 500mg"},
                ]
            }
        ).encode("utf-8")
        fake_response = MagicMock()
        fake_response.read.return_value = response_body
        fake_response.__enter__.return_value = fake_response
        fake_response.__exit__.return_value = False

        with patch("urllib.request.urlopen", return_value=fake_response):
            result = AnthropicOcrProvider().extract_text(io.BytesIO(b"fake-image-bytes"), mime_type="image/jpeg")

        self.assertEqual(result.text, "Amoxicilline 500mg")

    @override_settings(ANTHROPIC_API_KEY="test-key", ANTHROPIC_OCR_MODEL="claude-sonnet-5")
    def test_a_safety_refusal_raises_provider_error(self):
        response_body = json.dumps({"stop_reason": "refusal", "content": []}).encode("utf-8")
        fake_response = MagicMock()
        fake_response.read.return_value = response_body
        fake_response.__enter__.return_value = fake_response
        fake_response.__exit__.return_value = False

        with patch("urllib.request.urlopen", return_value=fake_response):
            with self.assertRaises(OcrProviderError):
                AnthropicOcrProvider().extract_text(io.BytesIO(b"fake-image-bytes"), mime_type="image/jpeg")

    @override_settings(ANTHROPIC_API_KEY="test-key")
    def test_http_error_raises_provider_error(self):
        error = HTTPError(url="", code=401, msg="unauthorized", hdrs=None, fp=io.BytesIO(b"bad key"))
        with patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(OcrProviderError):
                AnthropicOcrProvider().extract_text(io.BytesIO(b"fake-image-bytes"), mime_type="image/jpeg")

    @override_settings(ANTHROPIC_API_KEY="test-key")
    def test_network_error_raises_provider_error(self):
        with patch("urllib.request.urlopen", side_effect=URLError("no route to host")):
            with self.assertRaises(OcrProviderError):
                AnthropicOcrProvider().extract_text(io.BytesIO(b"fake-image-bytes"), mime_type="image/jpeg")


class MergeReaderResultsTests(TestCase):
    """
    Pure geometry/logic, no torch or the easyocr package needed - runs in every environment,
    unlike the real-inference tests below. Pins the region-merging fix: without it, running
    two readers (en+fr, en+ar) over the same image duplicated every detected line and, worse,
    kept whichever reader happened to run last even when its transcription was garbage (see
    docs/AI_FEATURES.md §2 for the "PANADOL 500MG" -> "P٥٧A٥٥L5٥٥MIG" repro that motivated
    this).
    """

    def test_same_region_keeps_the_higher_confidence_transcription(self):
        from apps.prescriptions.services.ocr.easyocr_provider import _merge_reader_results

        bbox = [[10, 10], [100, 10], [100, 30], [10, 30]]
        nearby_bbox = [[12, 11], [102, 11], [102, 31], [12, 31]]
        results_by_reader = [
            [(bbox, "PANADOL 500MG", 0.70)],
            [(nearby_bbox, "P٥٧A٥٥L5٥٥MIG", 0.20)],
        ]

        merged = _merge_reader_results(results_by_reader)

        self.assertEqual(merged, [("PANADOL 500MG", 0.70)])

    def test_distinct_regions_are_both_kept(self):
        from apps.prescriptions.services.ocr.easyocr_provider import _merge_reader_results

        bbox_a = [[10, 10], [100, 10], [100, 30], [10, 30]]
        bbox_b = [[10, 200], [100, 200], [100, 220], [10, 220]]
        results_by_reader = [[(bbox_a, "PANADOL 500MG", 0.7)], [(bbox_b, "دوليبران", 0.8)]]

        merged = _merge_reader_results(results_by_reader)

        self.assertEqual(set(merged), {("PANADOL 500MG", 0.7), ("دوليبران", 0.8)})

    def test_no_detections_returns_empty(self):
        from apps.prescriptions.services.ocr.easyocr_provider import _merge_reader_results

        self.assertEqual(_merge_reader_results([[], []]), [])


@unittest.skipUnless(EASYOCR_AVAILABLE, "easyocr package not installed in this environment")
class EasyOcrProviderTests(TestCase):
    def test_rejects_an_unsupported_file_type(self):
        with self.assertRaises(UnsupportedFileType):
            EasyOcrProvider().extract_text(io.BytesIO(b"not an image"), mime_type="image/gif")

    def test_extracts_text_from_a_printed_image(self):
        image = _render_text_png("PANADOL 500MG")

        result = EasyOcrProvider().extract_text(image, mime_type="image/png")

        self.assertIn("PANADOL", result.text.upper())
        self.assertEqual(result.provider, "easyocr")

    def test_reports_a_confidence_score_for_a_clean_printed_image(self):
        image = _render_text_png("PANADOL 500MG")

        result = EasyOcrProvider().extract_text(image, mime_type="image/png")

        self.assertIsNotNone(result.confidence)
        self.assertGreaterEqual(result.confidence, 0)
        self.assertLessEqual(result.confidence, 1)

    @unittest.skipUnless(POPPLER_AVAILABLE, "poppler-utils (pdftoppm) not installed in this environment")
    def test_extracts_text_from_a_pdf(self):
        pdf = _render_text_pdf("PANADOL 500MG")

        result = EasyOcrProvider().extract_text(pdf, mime_type="application/pdf")

        self.assertIn("PANADOL", result.text.upper())

    @unittest.skipUnless(POPPLER_AVAILABLE, "poppler-utils (pdftoppm) not installed in this environment")
    def test_malformed_pdf_raises_a_provider_error_not_a_silent_empty_result(self):
        with self.assertRaises(OcrProviderError):
            EasyOcrProvider().extract_text(io.BytesIO(b"%PDF-1.4\nnot a real pdf"), mime_type="application/pdf")


class RegistryTests(TestCase):
    def test_known_providers_resolve(self):
        self.assertIsInstance(get_provider("tesseract"), TesseractOcrProvider)
        self.assertIsInstance(get_provider("easyocr"), EasyOcrProvider)
        self.assertIsInstance(get_provider("anthropic"), AnthropicOcrProvider)

    def test_unknown_provider_raises(self):
        with self.assertRaises(ValueError):
            get_provider("does-not-exist")
