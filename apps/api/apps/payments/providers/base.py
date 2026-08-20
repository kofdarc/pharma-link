from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ChargeResult:
    status: str
    external_reference: str = ""
    raw: dict[str, Any] | None = None
    failure_reason: str = ""


class PaymentProvider(ABC):
    """
    The one method a real gateway adapter needs: given a Payment, attempt to charge it and
    report back. Whichever Lebanese platform gets picked (Whish Money, OMT, Areeba, ...)
    plugs in as one more class here and a registry entry - checkout call sites never change.
    """

    code: str

    @abstractmethod
    def charge(self, payment) -> ChargeResult: ...

    @abstractmethod
    def refund(self, payment) -> ChargeResult: ...
