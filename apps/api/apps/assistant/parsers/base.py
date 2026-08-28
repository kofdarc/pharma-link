from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class ParserError(Exception):
    """A parser could not run at all (misconfigured, network, malformed response)."""


@dataclass(frozen=True)
class ParseResult:
    """
    What a parser decided the person meant.

    `intent` is a name, never an answer - no parser in this package produces user-facing text.
    That split is the whole safety design: a parser can be wrong about which of a persona's
    intents to run, and the worst it achieves is the wrong lookup for someone already entitled
    to it, because the sentence that ships is rendered from the tool result by
    apps.assistant.intents and never by the parser.
    """

    intent: str
    slots: dict = field(default_factory=dict)
    confidence: float = 0.0
    source: str = ""
    options: tuple[str, ...] = ()


class IntentParser(ABC):
    """
    Turns a message into an intent name from the persona's allowlist, or declines.

    Returning None means "no opinion" and hands the message to the next parser in the chain.
    It is a normal outcome, not an error - the keyword parser returns None constantly, which
    is exactly what makes it safe to run first for free.
    """

    code: str

    @abstractmethod
    def parse(self, message: str, persona) -> ParseResult | None: ...
