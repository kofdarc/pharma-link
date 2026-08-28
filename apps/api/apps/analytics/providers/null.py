from __future__ import annotations

from typing import Any

from apps.analytics.providers.base import AssistantProvider, AssistantProviderError, ChatResult


class NullAssistantProvider(AssistantProvider):
    """
    Default for settings.ANALYTICS_AI_PROVIDER: no external call, no cost, nothing to
    configure. Raises rather than silently returning something - apps.analytics.services.
    narrative already has exactly one failure path to fall back to the deterministic data
    behind the request (Smart Insights' rule-based cards), so "not configured" and "provider
    call failed" go through the same branch instead of the caller special-casing "none".
    """

    code = "none"

    def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 1024,
    ) -> ChatResult:
        raise AssistantProviderError("No AI provider is configured for this surface.")
