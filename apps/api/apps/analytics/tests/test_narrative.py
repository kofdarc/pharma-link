"""
Narrative digest (apps/analytics/services/narrative.py): the model narrates deterministic
insights/KPI numbers, never computes anything, and every call has to survive the model being
absent or broken - see docs/AI_FEATURES.md §5.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.accounts.models import UserRole
from apps.analytics.providers.base import AssistantProviderError, ChatResult
from apps.analytics.services.narrative import generate_digest
from apps.pharmacies.models import Pharmacy

CONFIGURED = override_settings(
    ANALYTICS_AI_PROVIDER="openai_compatible",
    ANALYTICS_AI_BASE_URL="https://example.test/v1",
    ANALYTICS_AI_API_KEY="key",
    ANALYTICS_AI_MODEL="test-model",
)


class NarrativeDigestTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.pharmacy = Pharmacy.objects.create(name="Cedar Care", area="Hamra", city="Beirut", phone="+961-1-000-000")
        self.user = get_user_model().objects.create_user(
            email="owner@cedar.test", password="Password123!", role=UserRole.PHARMACY_OWNER, pharmacy=self.pharmacy
        )

    @override_settings(ANALYTICS_AI_PROVIDER="none")
    def test_no_provider_configured_falls_back_and_is_marked_stale(self):
        # Pinned explicitly rather than relying on the settings.py default - a real
        # ANALYTICS_AI_PROVIDER in the developer's own .env would otherwise make this test
        # fire a live network call instead of exercising the fallback path.
        digest = generate_digest(self.pharmacy)

        self.assertTrue(digest["stale"])
        self.assertEqual(digest["provider"], "none")
        self.assertIn("fallback_reason", digest)
        self.assertTrue(digest["headline"])

    @CONFIGURED
    @patch("apps.analytics.services.narrative.get_provider")
    def test_provider_failure_falls_back_rather_than_erroring(self, mock_get_provider):
        mock_get_provider.return_value.complete.side_effect = AssistantProviderError("boom")

        digest = generate_digest(self.pharmacy)

        self.assertTrue(digest["stale"])
        self.assertEqual(digest["fallback_reason"], "boom")

    @CONFIGURED
    @patch("apps.analytics.services.narrative.get_provider")
    def test_empty_completion_text_falls_back(self, mock_get_provider):
        mock_get_provider.return_value.complete.return_value = ChatResult(text="   ", provider="openai_compatible")

        digest = generate_digest(self.pharmacy)

        self.assertTrue(digest["stale"])

    @CONFIGURED
    @patch("apps.analytics.services.narrative.get_provider")
    def test_successful_completion_is_split_into_paragraphs(self, mock_get_provider):
        mock_get_provider.return_value.complete.return_value = ChatResult(
            text="First paragraph.\n\nSecond paragraph.", provider="openai_compatible"
        )

        digest = generate_digest(self.pharmacy)

        self.assertFalse(digest["stale"])
        self.assertEqual(digest["provider"], "openai_compatible")
        self.assertEqual(digest["paragraphs"], ["First paragraph.", "Second paragraph."])

    @CONFIGURED
    @patch("apps.analytics.services.narrative.get_provider")
    def test_headline_is_the_top_insight_regardless_of_provider_text(self, mock_get_provider):
        mock_get_provider.return_value.complete.return_value = ChatResult(text="Some prose.", provider="openai_compatible")

        digest = generate_digest(self.pharmacy)

        # No insights exist for a pharmacy with no data - the deterministic no-standout line.
        self.assertEqual(digest["headline"], generate_digest(self.pharmacy)["headline"])
        self.assertNotIn("Some prose.", digest["headline"])

    @CONFIGURED
    @patch("apps.analytics.services.narrative.get_provider")
    def test_result_is_cached_so_the_provider_is_called_once_per_payload(self, mock_get_provider):
        mock_get_provider.return_value.complete.return_value = ChatResult(text="Steady trading this week.", provider="openai_compatible")

        generate_digest(self.pharmacy)
        generate_digest(self.pharmacy)

        self.assertEqual(mock_get_provider.return_value.complete.call_count, 1)

    def test_result_always_carries_a_generated_at_timestamp(self):
        digest = generate_digest(self.pharmacy)

        self.assertIn("generated_at", digest)
