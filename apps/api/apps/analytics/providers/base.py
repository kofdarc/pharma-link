from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChatResult:
    text: str
    provider: str
    # Populated only if a provider actually returns tool calls. Unused today - the narrative
    # digest (apps.analytics.services.narrative) makes one completion call with no tools -
    # kept on the type because OpenAiCompatibleProvider's response shape always carries it.
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] | None = None


class AssistantProviderError(Exception):
    """A provider's chat completion call failed (network, auth, rate limit, bad response, ...)."""


class AssistantProvider(ABC):
    """
    One method an AI-narration adapter needs: given a system prompt and a message history,
    return a completion. Mirrors apps.prescriptions.services.ocr.base.OcrProvider and
    apps.messaging.providers.base.WhatsAppProvider - a new backend plugs in as one class here
    plus a registry entry; call sites (apps.analytics.services.narrative) never change.

    Lives in apps.analytics, not apps.assistant, on purpose: apps.assistant's own design
    (apps.assistant.parsers) deliberately never lets a model produce user-facing prose - a
    model there only picks an intent name from a fixed allowlist, and the reply is always
    rendered by apps.assistant.intents from a tool result. The narrative digest is a different
    risk profile - a model summarising a fixed, already-computed KPI payload into prose for
    the pharmacy owner's own analytics screen - so it gets its own provider seam under the app
    that owns that screen, rather than being bolted onto a package built around the opposite
    guarantee. If another surface later wants the same OpenAI-compatible-gateway pattern, it
    should get its own small copy of this seam rather than share this one - see
    settings.ANALYTICS_AI_* vs settings.ASSISTANT_*, which are deliberately separate budgets.
    """

    code: str

    @abstractmethod
    def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 1024,
    ) -> ChatResult: ...
