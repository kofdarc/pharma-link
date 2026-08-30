"""
OpenAiVisionOcrProvider - vision-model transcription over an OpenAI-compatible
/chat/completions endpoint. HTTP is mocked: no network, no key needed to run this.
"""

import io
import json
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from django.test import TestCase, override_settings

from apps.prescriptions.services.ocr.base import OcrProviderError, UnsupportedFileType
from apps.prescriptions.services.ocr.openai_vision import OpenAiVisionOcrProvider

VISION_SETTINGS = dict(
    PRESCRIPTION_OCR_VISION_BASE_URL="https://gw.test/v1",
    PRESCRIPTION_OCR_VISION_API_KEY="vk-test",
    PRESCRIPTION_OCR_VISION_MODEL="some/vision-model",
)


def _chat_response(text: str):
    fake = MagicMock()
    fake.read.return_value = json.dumps({"choices": [{"message": {"content": text}}]}).encode("utf-8")
    fake.__enter__.return_value = fake
    fake.__exit__.return_value = False
    return fake


class OpenAiVisionOcrProviderTests(TestCase):
    def test_raises_when_not_configured(self):
        with self.assertRaises(OcrProviderError):
            OpenAiVisionOcrProvider().extract_text(io.BytesIO(b"img"), mime_type="image/png")

    @override_settings(**VISION_SETTINGS)
    def test_rejects_an_unsupported_file_type(self):
        with self.assertRaises(UnsupportedFileType):
            OpenAiVisionOcrProvider().extract_text(io.BytesIO(b"x"), mime_type="text/plain")

    @override_settings(**VISION_SETTINGS)
    def test_transcribes_an_image_via_a_data_url_image_block(self):
        with patch("urllib.request.urlopen", return_value=_chat_response("Panadol 500mg x30")) as mock_urlopen:
            result = OpenAiVisionOcrProvider().extract_text(io.BytesIO(b"fake-jpeg"), mime_type="image/jpeg")

        self.assertEqual(result.text, "Panadol 500mg x30")
        self.assertEqual(result.provider, "openai_vision")

        request = mock_urlopen.call_args[0][0]
        self.assertEqual(request.full_url, "https://gw.test/v1/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer vk-test")
        payload = json.loads(request.data)
        blocks = payload["messages"][0]["content"]
        self.assertEqual(blocks[0]["type"], "image_url")
        self.assertTrue(blocks[0]["image_url"]["url"].startswith("data:image/jpeg;base64,"))
        self.assertEqual(blocks[1]["type"], "text")

    @override_settings(**VISION_SETTINGS)
    def test_http_error_raises_provider_error(self):
        error = HTTPError(url="", code=402, msg="payment required", hdrs=None, fp=io.BytesIO(b"no credits"))
        with patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(OcrProviderError):
                OpenAiVisionOcrProvider().extract_text(io.BytesIO(b"img"), mime_type="image/png")

    @override_settings(**VISION_SETTINGS)
    def test_network_error_raises_provider_error(self):
        with patch("urllib.request.urlopen", side_effect=URLError("no route")):
            with self.assertRaises(OcrProviderError):
                OpenAiVisionOcrProvider().extract_text(io.BytesIO(b"img"), mime_type="image/png")

    @override_settings(**VISION_SETTINGS)
    def test_unreadable_response_raises_provider_error(self):
        bad = MagicMock()
        bad.read.return_value = b'{"choices": []}'
        bad.__enter__.return_value = bad
        bad.__exit__.return_value = False
        with patch("urllib.request.urlopen", return_value=bad):
            with self.assertRaises(OcrProviderError):
                OpenAiVisionOcrProvider().extract_text(io.BytesIO(b"img"), mime_type="image/png")

    def test_registered_in_the_provider_registry(self):
        from apps.prescriptions.services.ocr.registry import get_provider

        self.assertIsInstance(get_provider("openai_vision"), OpenAiVisionOcrProvider)
