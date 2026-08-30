"""
apps.common.openai_chat.chat_completion - the shared /chat/completions caller with a
single fallback endpoint. HTTP is mocked.
"""

import json
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from django.test import SimpleTestCase, override_settings

from apps.common.openai_chat import Endpoint, OpenAiChatError, chat_completion, fallback_endpoint

PRIMARY = Endpoint("https://primary.test/v1", "pk", "primary/model")


def _ok(content: str):
    fake = MagicMock()
    fake.read.return_value = json.dumps({"choices": [{"message": {"content": content}}]}).encode("utf-8")
    fake.__enter__.return_value = fake
    fake.__exit__.return_value = False
    return fake


def _http_500():
    return HTTPError(url="", code=500, msg="err", hdrs=None, fp=MagicMock(read=lambda: b"boom"))


class ChatCompletionTests(SimpleTestCase):
    def test_returns_primary_message_on_success(self):
        with patch("urllib.request.urlopen", return_value=_ok("hi")) as mock:
            message = chat_completion(PRIMARY, messages=[{"role": "user", "content": "x"}])
        self.assertEqual(message["content"], "hi")
        self.assertEqual(mock.call_count, 1)
        self.assertEqual(mock.call_args[0][0].full_url, "https://primary.test/v1/chat/completions")

    def test_no_fallback_configured_raises_after_primary_fails(self):
        with patch("urllib.request.urlopen", side_effect=_http_500()):
            with self.assertRaises(OpenAiChatError):
                chat_completion(PRIMARY, messages=[])

    @override_settings(
        LLM_FALLBACK_BASE_URL="https://fallback.test/v1",
        LLM_FALLBACK_API_KEY="fk",
        LLM_FALLBACK_MODEL="free/model",
    )
    def test_falls_back_to_the_shared_endpoint_when_primary_fails(self):
        with patch("urllib.request.urlopen", side_effect=[_http_500(), _ok("from fallback")]) as mock:
            message = chat_completion(PRIMARY, messages=[])
        self.assertEqual(message["content"], "from fallback")
        self.assertEqual(mock.call_count, 2)
        second_call = mock.call_args_list[1][0][0]
        self.assertEqual(second_call.full_url, "https://fallback.test/v1/chat/completions")
        self.assertEqual(second_call.get_header("Authorization"), "Bearer fk")
        self.assertEqual(json.loads(second_call.data)["model"], "free/model")

    @override_settings(
        LLM_FALLBACK_BASE_URL="https://fallback.test/v1",
        LLM_FALLBACK_API_KEY="fk",
        LLM_FALLBACK_MODEL="free/model",
    )
    def test_primary_success_does_not_touch_the_fallback(self):
        with patch("urllib.request.urlopen", return_value=_ok("primary")) as mock:
            chat_completion(PRIMARY, messages=[])
        self.assertEqual(mock.call_count, 1)

    @override_settings(
        LLM_FALLBACK_BASE_URL="https://fallback.test/v1",
        LLM_FALLBACK_API_KEY="fk",
        LLM_FALLBACK_MODEL="free/model",
    )
    def test_both_failing_raises(self):
        with patch("urllib.request.urlopen", side_effect=[_http_500(), _http_500()]):
            with self.assertRaises(OpenAiChatError):
                chat_completion(PRIMARY, messages=[])

    @override_settings(LLM_FALLBACK_BASE_URL="https://primary.test/v1", LLM_FALLBACK_API_KEY="pk", LLM_FALLBACK_MODEL="x")
    def test_fallback_identical_to_primary_is_not_retried(self):
        with patch("urllib.request.urlopen", side_effect=_http_500()) as mock:
            with self.assertRaises(OpenAiChatError):
                chat_completion(PRIMARY, messages=[])
        self.assertEqual(mock.call_count, 1)

    def test_unconfigured_primary_with_no_fallback_raises(self):
        with self.assertRaises(OpenAiChatError):
            chat_completion(Endpoint("", "", ""), messages=[])

    @override_settings(LLM_FALLBACK_BASE_URL="", LLM_FALLBACK_API_KEY="", LLM_FALLBACK_MODEL="")
    def test_fallback_endpoint_helper_none_when_unset(self):
        self.assertIsNone(fallback_endpoint())
