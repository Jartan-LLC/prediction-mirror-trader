from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from prediction_mirror.models.target import TargetConfig


class SignalType(Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass
class Signal:
    signal_type: SignalType
    target: TargetConfig
    platform: str
    market_id: str
    asset_id: str
    outcome: str
    target_delta: float
    target_prev_size: float
    target_price: float
    detected_at: datetime
