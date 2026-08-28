"""
apps/analytics/providers/: the OpenAI-compatible chat-completions adapter (any gateway that
speaks that shape - OpenRouter, OpenCode Zen's compatible-model family, Ollama, ...) and its
registry. Mocking style mirrors apps.prescriptions.tests.test_ocr.AnthropicOcrProviderTests.
"""

import io
import json
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from django.test import TestCase

from apps.analytics.providers.base import AssistantProviderError
from apps.analytics.providers.null import NullAssistantProvider
from apps.analytics.providers.openai_compatible import OpenAiCompatibleProvider
from apps.analytics.providers.registry import get_provider


def _fake_response(body: dict):
    fake_response = MagicMock()
    fake_response.read.return_value = json.dumps(body).encode("utf-8")
    fake_response.__enter__.return_value = fake_response
    fake_response.__exit__.return_value = False
    return fake_response


class OpenAiCompatibleProviderTests(TestCase):
    def _provider(self):
        return OpenAiCompatibleProvider(base_url="https://example.test/v1", api_key="test-key", model="test-model")

    def test_successful_completion(self):
        response_body = {"choices": [{"message": {"content": "Steady week.", "role": "assistant"}}]}

        with patch("urllib.request.urlopen", return_value=_fake_response(response_body)) as mock_urlopen:
            result = self._provider().complete(system="You narrate.", messages=[{"role": "user", "content": "{}"}])

        self.assertEqual(result.text, "Steady week.")
        self.assertEqual(result.provider, "openai_compatible")
        request = mock_urlopen.call_args[0][0]
        self.assertEqual(request.full_url, "https://example.test/v1/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
        payload = json.loads(request.data)
        self.assertEqual(payload["model"], "test-model")
        self.assertEqual(payload["messages"][0], {"role": "system", "content": "You narrate."})

    def test_tool_calls_are_parsed_when_present(self):
        response_body = {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [{"id": "call_1", "function": {"name": "stock_lookup", "arguments": '{"query": "panadol"}'}}],
                    }
                }
            ]
        }

        with patch("urllib.request.urlopen", return_value=_fake_response(response_body)):
            result = self._provider().complete(system="", messages=[])

        self.assertEqual(result.text, "")
        self.assertEqual(result.tool_calls, [{"id": "call_1", "name": "stock_lookup", "arguments": '{"query": "panadol"}'}])

    def test_http_error_raises_provider_error(self):
        error = HTTPError(url="", code=401, msg="unauthorized", hdrs=None, fp=io.BytesIO(b"bad key"))
        with patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(AssistantProviderError):
                self._provider().complete(system="", messages=[])

    def test_network_error_raises_provider_error(self):
        with patch("urllib.request.urlopen", side_effect=URLError("no route to host")):
            with self.assertRaises(AssistantProviderError):
                self._provider().complete(system="", messages=[])

    def test_response_with_no_choices_raises_provider_error(self):
        with patch("urllib.request.urlopen", return_value=_fake_response({"choices": []})):
            with self.assertRaises(AssistantProviderError):
                self._provider().complete(system="", messages=[])


class NullAssistantProviderTests(TestCase):
    def test_always_raises(self):
        with self.assertRaises(AssistantProviderError):
            NullAssistantProvider().complete(system="", messages=[])


class RegistryTests(TestCase):
    def test_none_ignores_config(self):
        provider = get_provider("none")
        self.assertIsInstance(provider, NullAssistantProvider)

    def test_openai_compatible_requires_full_config(self):
        with self.assertRaises(ValueError):
            get_provider("openai_compatible", base_url="", api_key="key", model="m")

    def test_openai_compatible_builds_with_full_config(self):
        provider = get_provider("openai_compatible", base_url="https://example.test/v1", api_key="key", model="m")
        self.assertIsInstance(provider, OpenAiCompatibleProvider)

    def test_unknown_provider_raises(self):
        with self.assertRaises(ValueError):
            get_provider("does-not-exist")
