"""
Turns a tool's JSON result into the sentence the person actually reads.

This is the generation half of a small, deliberately narrow RAG loop: retrieval is the
persona-scoped tool call in apps.assistant.tools (already access-controlled, already
tenant-scoped, already run before this module is reached), generation is this module asking a
model to describe exactly what came back. The model never chooses what to read and is never
given a tool of its own - it is handed a JSON object apps.assistant.services already decided
this caller may see, and asked to turn it into a sentence.

Inert until ASSISTANT_API_KEY and ASSISTANT_MODEL are set, same fallback shape as
apps.assistant.parsers.openrouter. Whether or not it runs, `compose()` never fails open: any
missing config, request error, or reply that states a fact absent from the tool result falls
back to the fixed template in apps.assistant.intents - which is why that template stays fully
maintained rather than becoming a "just in case" afterthought nobody reads.
"""

from __future__ import annotations

import json
import logging
import re

from django.conf import settings

from apps.common.openai_chat import Endpoint, OpenAiChatError, chat_completion

logger = logging.getLogger(__name__)

MAX_RESULT_CHARS = 4000
MAX_MESSAGE_CHARS = 500
MAX_REPLY_CHARS = 600

SYSTEM_PROMPT = """\
You write one short reply for a pharmacy platform's in-app assistant. You are given the exact
data already fetched for this person - a JSON object - and you describe what is in it. You did
not decide what to look up and you have no tools of your own; the lookup already happened
before you were called.

Rules, all of them absolute:
- State only what is in the JSON. Never add a number, price, date, name or status that is not
  there, and never fill a gap with typical- or plausible-sounding information.
- Copy numbers, prices and dates exactly as they appear in the JSON - do not reformat, round,
  convert currency, or spell a date out in words.
- If the JSON is empty or shows no results, say so plainly. Do not guess why.
- Never give medical advice, dosage guidance, or a view on whether one product can replace
  another, even if the JSON is about medicines. Describe the data, nothing else - a clinical
  question would not have reached you in the first place if this reply were meant to answer it.
- Two or three short sentences at most. No headings, no bullet points, no bold text.
- Reply in the same language the person's message is written in.
- Output the reply itself and nothing else - no preamble, no surrounding quotation marks, no
  explanation of what you are doing or that you were given data.

Who you are talking to: {audience}
They asked: {message}
This data answers: {intent_description}
"""


def compose(*, intent, result: dict, message: str, persona) -> str | None:
    """
    Ask the model to describe `result` in one short reply, or decline.

    Returns None - meaning "render the template instead" - whenever the composer is
    unconfigured, the request fails, or the reply does not pass the grounding check. The
    caller (apps.assistant.services) always has a working template to fall back to, so a
    composer outage costs a duller reply, never a broken one.
    """
    if not settings.ASSISTANT_API_KEY or not settings.ASSISTANT_MODEL:
        return None
    if not result:
        return None

    payload_json = json.dumps(result, default=str)[:MAX_RESULT_CHARS]
    system = SYSTEM_PROMPT.format(
        audience=persona.label,
        message=message[:MAX_MESSAGE_CHARS],
        intent_description=intent.description,
    )
    messages = [
        {"role": "system", "content": system},
        # Delimited the same way the intent parser delimits the user's message - a visual
        # boundary marking where untrusted content starts, not a security control on its
        # own. The actual control is the grounding check below, which does not care what the
        # model was talked into writing, only whether the numbers in it are real.
        {"role": "user", "content": f"<data>\n{payload_json}\n</data>"},
    ]
    try:
        message = chat_completion(
            Endpoint(settings.ASSISTANT_BASE_URL, settings.ASSISTANT_API_KEY, settings.ASSISTANT_MODEL),
            messages=messages,
            temperature=0.3,
            # The reply is two or three sentences, but a "thinking" fallback model spends
            # tokens reasoning before it - headroom so it still finishes the sentence.
            max_tokens=1500,
            timeout=settings.ASSISTANT_TIMEOUT_SECONDS,
            extra_headers={"HTTP-Referer": settings.ASSISTANT_REFERER, "X-Title": "HealthConnect assistant"},
        )
    except OpenAiChatError:
        logger.warning("Assistant composer request failed", exc_info=True)
        return None

    reply = _clean(message.get("content"))
    if not reply:
        return None
    if not is_grounded(reply, result):
        logger.warning("Assistant composer reply failed the grounding check for intent %r, falling back to template", intent.name)
        return None
    return reply[:MAX_REPLY_CHARS]


def _clean(raw) -> str:
    """Strip the wrapping a chat model adds despite being told not to: code fences, quotes."""
    if not isinstance(raw, str):
        return ""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
    quote_pairs = ('""', "''", "“”", "‘’")
    if len(text) >= 2 and any(text[0] == open_q and text[-1] == close_q for open_q, close_q in quote_pairs):
        text = text[1:-1].strip()
    return text


# The decimal group requires a digit after the dot. Without that, "...costs 2.25." matched
# past the sentence's own full stop as "2.25." while the source data (no trailing sentence to
# end) held only "2.25" - two different strings, a false rejection on every reply that happens
# to end on a number. Caught live: a medicine name containing digits ("xyzabc123") at the end
# of a sentence tripped this exact way and discarded an otherwise-correct composed reply.
NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers(text: str) -> set[str]:
    return {token.replace(",", "") for token in NUMBER_RE.findall(text)}


def is_grounded(reply: str, result: dict) -> bool:
    """
    Every number the reply states has to actually appear somewhere in the data it describes.

    A blunt check on purpose: it does not know which field a number came from or what unit it
    is in, only whether those digits exist somewhere in the source JSON. That is enough to
    catch what matters - an invented stock count, price or day figure has essentially no
    chance of coincidentally matching a real substring in the data it was supposed to
    describe - without being so exact that ordinary rephrasing (plural forms, word order,
    dropping trailing zeros a model tends to drop anyway) trips a reply that is actually fine.
    A reply with no numbers in it always passes, since there is nothing to check.
    """
    reply_numbers = _numbers(reply)
    if not reply_numbers:
        return True
    return reply_numbers <= _numbers(json.dumps(result, default=str))
