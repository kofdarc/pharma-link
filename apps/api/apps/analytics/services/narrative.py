"""
Free-form narrative digest over the deterministic numbers apps.analytics.services.kpis and
.insights already compute - see docs/AI_FEATURES.md §5. The model only narrates: every number
it can mention already came from generate_insights()/overview()/movement_classification()/
demand_signals() elsewhere in this app. It is never asked to compute anything, and never given
a channel to write beyond prose - no tools, nothing it can act on.

Failure is not something this can expose to a pharmacy owner's normal analytics screen: if
settings.ANALYTICS_AI_PROVIDER is unset, or the call fails for any reason (bad key, network,
rate limit, malformed response), generate_digest() falls back to the same rule-based Smart
Insights cards the Insights tab already renders, and marks the result `stale` so the caller
can say so rather than presenting AI prose that was never actually generated.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from apps.analytics.providers.base import AssistantProviderError
from apps.analytics.providers.registry import get_provider
from apps.analytics.services import insights as insights_service
from apps.analytics.services import kpis

# The underlying numbers don't move faster than sales/stock do, so a stale digest for a few
# hours is a non-issue - and it's what keeps a pharmacy owner refreshing the tab from costing
# a fresh provider call every time.
CACHE_TTL_SECONDS = 60 * 60 * 12
# Generous on purpose: a reasoning-capable model (verified against a free OpenCode Zen model)
# spends a meaningful chunk of this budget on hidden/visible deliberation before it writes the
# actual digest, and 700 wasn't enough headroom for it to ever reach the answer - the response
# came back as truncated scratch-work instead of prose. This costs more per call on a model
# that bills output tokens; it's the tradeoff for not losing the answer to truncation.
MAX_TOKENS = 2500
NO_STANDOUT_HEADLINE = "Trading normally - nothing crossed a threshold worth flagging today."

SYSTEM_PROMPT = """\
You write a short daily digest for a pharmacy owner, from numbers already computed by their
own analytics system. You are a narrator, not an analyst: every figure you use must come from
the JSON payload you are given, quoted exactly as given (same units, same currency, same
rounding) - never estimate, round differently, or invent a number that is not in the payload.

Write two or three short paragraphs, plain language, no headings, no bullet points, separated
by a blank line. Lead with whatever in the payload's "insights" list most needs the owner's
attention today (it is already ranked critical/warning/opportunity/info), then note anything
else worth knowing from the rest of the payload.

You may connect two facts that happened over the same window ("X fell while Y was out of
stock the same week") but only as an observed correlation, never as a claimed cause - do not
write "because", "likely due to", "caused by", or any other causal claim connecting two
numbers. If you are not confident two figures are related, mention them as separate
observations instead of joining them.

Reply in the language named by the payload's "locale" field. Address the reader as "you" at
most once; this is a summary, not a to-do list.

Output only the finished digest text. Do not narrate your own process, list steps you're
about to take, or think out loud before writing it - if you need to work something out, do
that silently and reply with just the final paragraphs.
"""


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _build_payload(pharmacy, *, locale: str) -> dict:
    overview = kpis.overview(pharmacy)
    movement = kpis.movement_classification(pharmacy, days=30, limit=5)
    demand = kpis.demand_signals(pharmacy, days=30, limit=5)
    payload = {
        "locale": locale,
        "pharmacy": overview["pharmacy"],
        "stock": overview["stock"],
        "sales_30d": overview["sales_30d"],
        "sales_7d": overview["sales_7d"],
        "turnover": overview["turnover"],
        "platform": overview["platform"],
        "top_movers": movement["top_movers"],
        "dead_stock": movement["dead_stock"],
        "unmet_demand": demand["signals"],
        # Same cards the Insights tab renders (apps.analytics.services.insights) - the model
        # narrates these, it does not derive its own reading of the raw numbers above them.
        "insights": insights_service.generate_insights(pharmacy),
    }
    return _jsonable(payload)


def _split_paragraphs(text: str) -> list[str]:
    blocks = [block.strip() for block in text.split("\n\n") if block.strip()]
    if len(blocks) <= 1:
        blocks = [block.strip() for block in text.split("\n") if block.strip()]
    return blocks or [text.strip()]


def _cache_key(pharmacy_id, payload: dict) -> str:
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
    return f"analytics:digest:{pharmacy_id}:{digest}"


def _fallback(*, headline: str, generated_insights: list[dict], grounded_on: list[str], reason: str) -> dict:
    paragraphs = [item["detail"] for item in generated_insights if item.get("detail")] or [headline]
    return {
        "headline": headline,
        "paragraphs": paragraphs,
        "grounded_on": grounded_on,
        "provider": "none",
        "stale": True,
        "fallback_reason": reason,
    }


def generate_digest(pharmacy, *, locale: str = "en") -> dict:
    """
    Returns {headline, paragraphs, grounded_on, provider, stale, generated_at[, fallback_reason]}.
    Always succeeds - see module docstring for the fallback contract. `headline` is always the
    top-ranked Smart Insights title (deterministic, same language as the rest of that feature
    today), even when the model produced the paragraphs - so the one line every caller can
    render unconditionally never depends on the provider having worked.
    """
    payload = _build_payload(pharmacy, locale=locale)
    generated_insights = payload["insights"]
    headline = generated_insights[0]["title"] if generated_insights else NO_STANDOUT_HEADLINE
    grounded_on = [item["id"] for item in generated_insights]

    cache_key = _cache_key(pharmacy.id, payload)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        provider = get_provider(
            settings.ANALYTICS_AI_PROVIDER,
            base_url=settings.ANALYTICS_AI_BASE_URL,
            api_key=settings.ANALYTICS_AI_API_KEY,
            model=settings.ANALYTICS_AI_MODEL,
        )
        completion = provider.complete(
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": json.dumps(payload, default=str)}],
            max_tokens=MAX_TOKENS,
        )
        text = completion.text.strip()
        if not text:
            raise AssistantProviderError("Provider returned an empty response.")
        result = {
            "headline": headline,
            "paragraphs": _split_paragraphs(text),
            "grounded_on": grounded_on,
            "provider": completion.provider,
            "stale": False,
        }
    except (AssistantProviderError, ValueError) as exc:
        result = _fallback(headline=headline, generated_insights=generated_insights, grounded_on=grounded_on, reason=str(exc))

    result["generated_at"] = timezone.now().isoformat()
    cache.set(cache_key, result, CACHE_TTL_SECONDS)
    return result
