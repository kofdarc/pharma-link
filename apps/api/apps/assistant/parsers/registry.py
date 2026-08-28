from apps.assistant.parsers.base import IntentParser, ParseResult, ParserError
from apps.assistant.parsers.keyword import KeywordIntentParser
from apps.assistant.parsers.openrouter import OpenRouterIntentParser

# The keyword parser is not in here on purpose: it is not a choice. It always runs first, for
# free, and ASSISTANT_PARSER only decides what - if anything - runs behind it when it abstains.
_PARSERS: dict[str, IntentParser] = {
    OpenRouterIntentParser.code: OpenRouterIntentParser(),
}

KEYWORD_ONLY = "keyword"


def get_fallback_parser(code: str) -> IntentParser | None:
    """The parser that handles what keywords could not. `keyword` means "nothing behind it"."""
    if code == KEYWORD_ONLY:
        return None
    try:
        return _PARSERS[code]
    except KeyError:
        raise ValueError(f"Unknown assistant parser '{code}'.") from None


__all__ = ["IntentParser", "ParseResult", "ParserError", "KeywordIntentParser", "get_fallback_parser", "KEYWORD_ONLY"]
