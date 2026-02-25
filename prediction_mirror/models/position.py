from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class TargetPosition:
    target_address: str
    platform: str
    market_id: str
    asset_id: str
    outcome: str
    size: float
    avg_price: float
    current_price: float
    snapshot_time: datetime


@dataclass
class OurPosition:
    market_id: str
    asset_id: str
    platform: str
    outcome: str
    size: float
    avg_entry_price: float
    total_cost: float
    realized_pnl: float
    source_target: str
    dry_run: bool
    updated_at: datetime
