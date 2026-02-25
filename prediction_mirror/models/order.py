from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from prediction_mirror.models.signal import Signal


class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass
class SizedOrder:
    signal: Signal
    side: OrderSide
    asset_id: str
    price: float
    size: float
    usd_amount: float
    dry_run: bool


@dataclass
class OrderResult:
    order: SizedOrder
    success: bool
    order_id: str | None
    fill_price: float | None
    fill_size: float | None
    error: str | None
    executed_at: datetime
