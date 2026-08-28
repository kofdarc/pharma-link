"""
What must hold:
  - the composer is inert (returns None, falls back to template) with no key configured
  - it never runs at all for an intent with no tool behind it, or with an empty result
  - a reply is accepted only when every number in it actually appears in the tool's own data
  - an invented number - one that doesn't appear anywhere in the source JSON - is rejected
  - wrapping (code fences, quotes) a model adds despite instructions is stripped before checking
  - a composer failure never breaks a turn: services.answer() still returns the template reply
"""

from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.assistant import composer, personas, services
from apps.assistant.intents import get_intent


class GroundingCheckTests(TestCase):
    def test_a_reply_with_no_numbers_always_passes(self):
        self.assertTrue(composer.is_grounded("No results were found.", {"query": "panadol"}))

    def test_a_number_present_in_the_data_passes(self):
        result = {"query": "panadol", "results": [{"medicine": "Panadol", "unit_price": "2.25", "available_up_to": 10}]}
        self.assertTrue(composer.is_grounded("Panadol is available for 2.25, up to 10 units.", result))

    def test_an_invented_number_is_rejected(self):
        result = {"query": "panadol", "results": [{"medicine": "Panadol", "unit_price": "2.25"}]}
        self.assertFalse(composer.is_grounded("Panadol is available for 9.99.", result))

    def test_an_invented_count_is_rejected(self):
        result = {"pending_count": 2, "applications": []}
        self.assertFalse(composer.is_grounded("You have 7 applications pending.", result))

    def test_comma_formatted_numbers_still_match(self):
        result = {"revenue": "1234.50"}
        self.assertTrue(composer.is_grounded("Revenue came to 1,234.50.", result))

    def test_a_number_at_the_end_of_a_sentence_is_not_glued_to_the_full_stop(self):
        # Caught live: a query containing digits ("xyzabc123") echoed at a sentence's end
        # matched as "123." against the data's bare "123", and a correct reply was discarded.
        result = {"query": "xyzabc123", "results": []}
        self.assertTrue(composer.is_grounded("There are no results for xyzabc123.", result))

    def test_a_decimal_at_the_end_of_a_sentence_is_not_glued_to_the_full_stop(self):
        result = {"unit_price": "2.25"}
        self.assertTrue(composer.is_grounded("It costs 2.25.", result))


class CleanTests(TestCase):
    def test_strips_code_fence_wrapping(self):
        self.assertEqual(composer._clean("```\nHello there.\n```"), "Hello there.")

    def test_strips_surrounding_quotes(self):
        self.assertEqual(composer._clean('"Hello there."'), "Hello there.")

    def test_leaves_ordinary_text_untouched(self):
        self.assertEqual(composer._clean("Hello there."), "Hello there.")

    def test_non_string_input_is_empty(self):
        self.assertEqual(composer._clean(None), "")


class ComposerConfigTests(TestCase):
    """With no key configured - the state of every test and every dev environment by default -
    the composer must not attempt a network call at all, and must decline cleanly."""

    def setUp(self):
        self.intent = get_intent("search_availability")
        self.persona = personas.PERSONAS[personas.GUEST]

    @override_settings(ASSISTANT_API_KEY="", ASSISTANT_MODEL="")
    def test_returns_none_with_no_key_configured(self):
        result = composer.compose(intent=self.intent, result={"query": "panadol", "results": []}, message="who has panadol", persona=self.persona)
        self.assertIsNone(result)

    @override_settings(ASSISTANT_API_KEY="test-key", ASSISTANT_MODEL="openai/gpt-4o-mini")
    def test_returns_none_for_an_empty_result(self):
        result = composer.compose(intent=self.intent, result={}, message="who has panadol", persona=self.persona)
        self.assertIsNone(result)

    @override_settings(ASSISTANT_API_KEY="test-key", ASSISTANT_MODEL="openai/gpt-4o-mini")
    def test_a_request_failure_returns_none_rather_than_raising(self):
        with patch("apps.assistant.composer.urllib.request.urlopen", side_effect=OSError("network down")):
            result = composer.compose(intent=self.intent, result={"query": "panadol", "results": []}, message="who has panadol", persona=self.persona)
        self.assertIsNone(result)

    @override_settings(ASSISTANT_API_KEY="test-key", ASSISTANT_MODEL="openai/gpt-4o-mini")
    def test_an_ungrounded_completion_is_rejected(self):
        fake_response = _fake_completion("Panadol is available for 9.99, an invented price.")
        with patch("apps.assistant.composer.urllib.request.urlopen", return_value=fake_response):
            result = composer.compose(
                intent=self.intent,
                result={"query": "panadol", "results": [{"medicine": "Panadol", "unit_price": "2.25"}]},
                message="who has panadol",
                persona=self.persona,
            )
        self.assertIsNone(result)

    @override_settings(ASSISTANT_API_KEY="test-key", ASSISTANT_MODEL="openai/gpt-4o-mini")
    def test_a_grounded_completion_is_accepted(self):
        fake_response = _fake_completion("Panadol is available for 2.25.")
        with patch("apps.assistant.composer.urllib.request.urlopen", return_value=fake_response):
            result = composer.compose(
                intent=self.intent,
                result={"query": "panadol", "results": [{"medicine": "Panadol", "unit_price": "2.25"}]},
                message="who has panadol",
                persona=self.persona,
            )
        self.assertEqual(result, "Panadol is available for 2.25.")


class ComposerIntegrationTests(TestCase):
    """The composer is opt-in per environment; with it unconfigured, a full turn through
    services.answer() must behave exactly as it did before the composer existed."""

    @override_settings(ASSISTANT_API_KEY="", ASSISTANT_MODEL="")
    def test_answer_falls_back_to_the_template_with_no_composer_configured(self):
        out = services.answer(user=None, message="who has panadol")
        self.assertEqual(out["intent"], "search_availability")
        self.assertIn("couldn't find", out["reply"])  # the template's own wording for no results

    @override_settings(ASSISTANT_API_KEY="test-key", ASSISTANT_MODEL="openai/gpt-4o-mini")
    def test_a_composer_failure_still_returns_the_template_reply(self):
        with patch("apps.assistant.composer.urllib.request.urlopen", side_effect=OSError("network down")):
            out = services.answer(user=None, message="who has panadol")
        self.assertEqual(out["intent"], "search_availability")
        self.assertTrue(out["reply"])

    def test_the_composer_is_never_consulted_for_a_toolless_intent(self):
        with patch("apps.assistant.composer.compose") as mocked:
            services.answer(user=None, message="hi")
        mocked.assert_not_called()


def _fake_completion(text: str):
    import io
    import json as jsonlib

    payload = jsonlib.dumps({"choices": [{"message": {"content": text}}]}).encode("utf-8")

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    return _Resp(payload)
