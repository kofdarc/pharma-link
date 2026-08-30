from __future__ import annotations

from typing import Any

from apps.analytics.providers.base import AssistantProvider, AssistantProviderError, ChatResult
from apps.common.openai_chat import Endpoint, OpenAiChatError, chat_completion

REQUEST_TIMEOUT_SECONDS = 30
# Some gateways sit behind Cloudflare bot rules that block urllib's default
# "User-Agent: Python-urllib/x.y" outright (verified against OpenCode Zen: that exact string
# gets a 403/error-1010 bot-signature block, while any other UA - or none at all - passes).
# Sent explicitly so this adapter doesn't silently start failing depending on which gateway
# it's pointed at.
USER_AGENT = "PharmaLink-Analytics/1.0"


class OpenAiCompatibleProvider(AssistantProvider):
    """
    One adapter for every gateway that speaks the OpenAI `/chat/completions` shape:
    OpenRouter, OpenCode Zen (its `/chat/completions`-family models only - its OpenAI/
    Anthropic/Google-native models route through different endpoints this class does not
    speak), a local Ollama server, Groq, and friends. Same one-class-per-shape precedent as
    apps.prescriptions.services.ocr.anthropic.AnthropicOcrProvider and apps.assistant.parsers.
    openrouter.OpenRouterIntentParser: stdlib `urllib` rather than an SDK dependency, since the
    request/response shape is small and stable.

    `base_url` and `api_key` are passed in per call rather than read from settings directly,
    since get_provider() in registry.py builds one instance per configured surface (see
    settings.ANALYTICS_AI_*) rather than a shared module-level singleton.
    """

    code = "openai_compatible"

    def __init__(self, *, base_url: str, api_key: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 1024,
    ) -> ChatResult:
        try:
            choice = chat_completion(
                Endpoint(self.base_url, self.api_key, self.model),
                messages=[{"role": "system", "content": system}, *messages],
                max_tokens=max_tokens,
                tools=tools,
                timeout=REQUEST_TIMEOUT_SECONDS,
                user_agent=USER_AGENT,
            )
        except OpenAiChatError as exc:
            raise AssistantProviderError(f"{self.code} request failed: {exc}") from exc

        tool_calls = [
            {
                "id": call.get("id", ""),
                "name": call.get("function", {}).get("name", ""),
                "arguments": call.get("function", {}).get("arguments", "{}"),
            }
            for call in (choice.get("tool_calls") or [])
        ]
        return ChatResult(text=choice.get("content") or "", provider=self.code, tool_calls=tool_calls, raw=choice)
