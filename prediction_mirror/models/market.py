from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class MarketStatus(Enum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


@dataclass
class Market:
    market_id: str
    platform: str
    question: str
    outcomes: list[str]
    status: MarketStatus
    resolution_outcome: str | None = None
