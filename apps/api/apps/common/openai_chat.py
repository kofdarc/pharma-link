"""
One `/chat/completions` caller every OpenAI-compatible surface in this codebase routes
through, so a single shared fallback endpoint (``settings.LLM_FALLBACK_*``) can stand in
for any primary that is down or rate-limited.

The primaries stay deliberately separate - the assistant, the analytics digest, and the
prescription pipeline each keep their own key, model, budget and prompt (see the design
note in apps.analytics.providers.base). This module adds only the shared *last resort*,
tried after a caller's own endpoint raises and before that caller degrades to its
deterministic path.

stdlib urllib, no SDK - the request/response shape is small and stable, matching the
outbound-HTTP precedent across the codebase.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, NamedTuple

from django.conf import settings

DEFAULT_USER_AGENT = "PharmaLink/1.0"
DEFAULT_TIMEOUT_SECONDS = 30


class Endpoint(NamedTuple):
    base_url: str
    api_key: str
    model: str

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)


class OpenAiChatError(Exception):
    """Every configured endpoint (the caller's own plus the shared fallback) failed, or
    none were configured."""


def fallback_endpoint() -> Endpoint | None:
    endpoint = Endpoint(
        settings.LLM_FALLBACK_BASE_URL,
        settings.LLM_FALLBACK_API_KEY,
        settings.LLM_FALLBACK_MODEL,
    )
    return endpoint if endpoint.configured else None


def chat_completion(
    primary: Endpoint,
    *,
    messages: list[dict[str, Any]],
    temperature: float = 0.0,
    max_tokens: int = 1024,
    response_format: dict | None = None,
    tools: list[dict] | None = None,
    extra_headers: dict[str, str] | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    user_agent: str = DEFAULT_USER_AGENT,
    use_fallback: bool = True,
) -> dict[str, Any]:
    """POST ``messages`` to ``primary``; on any failure, retry once against the shared
    ``settings.LLM_FALLBACK_*`` endpoint (unless ``use_fallback=False`` or it isn't
    configured / duplicates the primary).

    Returns the assistant message dict - ``{"content": str|None, "tool_calls": [...]}`` -
    from the first endpoint that answers. Raises :class:`OpenAiChatError` only when every
    endpoint fails or none is configured. Each endpoint contributes its own model, so the
    fallback can run a different (e.g. free) model than the primary.
    """
    endpoints: list[Endpoint] = [primary] if primary.configured else []
    if use_fallback:
        fb = fallback_endpoint()
        if fb and (fb.base_url, fb.api_key) != (primary.base_url, primary.api_key):
            endpoints.append(fb)
    if not endpoints:
        raise OpenAiChatError("No chat endpoint configured (primary unset and no LLM_FALLBACK_*).")

    last_error = "unknown"
    for endpoint in endpoints:
        body: dict[str, Any] = {
            "model": endpoint.model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if response_format:
            body["response_format"] = response_format
        if tools:
            body["tools"] = tools

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {endpoint.api_key}",
            "User-Agent": user_agent,
        }
        if extra_headers:
            headers.update(extra_headers)

        request = urllib.request.Request(
            f"{endpoint.base_url.rstrip('/')}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
            return data["choices"][0]["message"]
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            last_error = f"HTTP {exc.code}: {detail}"[:400]
        except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            last_error = str(exc)[:400]

    raise OpenAiChatError(f"All chat endpoints failed - last error: {last_error}")
