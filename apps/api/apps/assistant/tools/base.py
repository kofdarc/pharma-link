from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class ToolContext:
    """
    Everything a tool handler is allowed to know.

    `user` comes off the authenticated request and nothing else - never from the message, the
    parsed slots, or the request body. That is what makes "show me order 4821 for another
    customer" unanswerable rather than merely discouraged: no handler accepts an identity
    argument, so there is no place for the model, or the person typing, to put one.

    `slots` is parsed from the message and is therefore untrusted. Handlers treat it as search
    input only - a medicine name, a day count - and never as a key into somebody's records.
    """

    user: Any = None
    slots: dict[str, Any] = field(default_factory=dict)

    def text(self, name: str, default: str = "") -> str:
        value = self.slots.get(name)
        return value.strip() if isinstance(value, str) else default

    def number(self, name: str, default: int, *, low: int, high: int) -> int:
        try:
            return max(low, min(high, int(self.slots.get(name, default))))
        except (TypeError, ValueError):
            return default


@dataclass(frozen=True)
class ToolSpec:
    """
    A read-only lookup the assistant can run.

    Every tool in this package is a read. None of them writes, cancels, accepts or approves
    anything, and that is a design constraint rather than an accident of what has been built
    so far: it means the worst outcome of a mis-parsed message, or of a successful prompt
    injection once the model parser is switched on, is that the assistant reads the wrong
    thing for the person who is already entitled to read it - never that it does something on
    their behalf.
    """

    name: str
    handler: Callable[[ToolContext], dict]
    description: str = ""
