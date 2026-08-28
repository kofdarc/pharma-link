"""
Deciding what a message meant, cheapest parser first.

Keywords always run first and cost nothing. Only what they decline goes to the configured
fallback parser, and only if one is configured at all. A fallback that errors - misconfigured,
rate limited, endpoint down - is logged and treated as another abstention, so the assistant
degrades to "I couldn't work out what you're after" rather than to a 500.
"""

from __future__ import annotations

import logging

from django.conf import settings

from apps.assistant.parsers.base import ParseResult, ParserError
from apps.assistant.parsers.keyword import KeywordIntentParser
from apps.assistant.parsers.registry import get_fallback_parser

logger = logging.getLogger(__name__)

_keyword = KeywordIntentParser()


def resolve(message: str, persona) -> ParseResult:
    result = _keyword.parse(message, persona)
    if result is not None:
        return result

    result = _fallback(message, persona)
    if result is not None:
        return result

    return ParseResult(intent="unknown", source="none")


def _fallback(message: str, persona) -> ParseResult | None:
    try:
        parser = get_fallback_parser(settings.ASSISTANT_PARSER)
    except ValueError:
        logger.exception("ASSISTANT_PARSER names a parser that does not exist")
        return None
    if parser is None:
        return None

    try:
        return parser.parse(message, persona)
    except ParserError:
        # Deliberately not re-raised. The assistant is a convenience surface; an unreachable
        # classifier should cost the person one unhelpful reply, not an error page.
        logger.warning("Assistant fallback parser %r failed", parser.code, exc_info=True)
        return None
