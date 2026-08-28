from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from apps.analytics.providers.base import AssistantProvider, AssistantProviderError, ChatResult

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
        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, *messages],
        }
        if tools:
            body["tools"] = tools

        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": USER_AGENT,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise AssistantProviderError(f"{self.code} request failed: HTTP {exc.code}: {detail}"[:500]) from exc
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise AssistantProviderError(f"{self.code} request failed: {exc}") from exc
        except (json.JSONDecodeError, KeyError, IndexError) as exc:
            raise AssistantProviderError(f"{self.code} returned a response this adapter could not parse: {exc}") from exc

        try:
            choice = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AssistantProviderError(f"{self.code} response had no completion: {json.dumps(data)[:500]}") from exc

        tool_calls = [
            {
                "id": call.get("id", ""),
                "name": call.get("function", {}).get("name", ""),
                "arguments": call.get("function", {}).get("arguments", "{}"),
            }
            for call in (choice.get("tool_calls") or [])
        ]
        return ChatResult(text=choice.get("content") or "", provider=self.code, tool_calls=tool_calls, raw=data)
