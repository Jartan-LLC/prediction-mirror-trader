from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TargetConfig:
    label: str
    platform: str
    address: str
    allocation_pct: float
    multiplier: float = 1.0
    enabled: bool = True
    sizing_mode: str = "conviction"
    history_window: int = 50
    min_history: int = 10
    cold_start_pct: float = 0.0
    trade_size_pct: float = 1.0
    aggregation_seconds: int = 7

    def __post_init__(self):
        if not self.label:
            raise ValueError("label must not be empty")
        if self.allocation_pct < 0 or self.allocation_pct > 100:
            raise ValueError(f"allocation_pct must be 0-100, got {self.allocation_pct}")
        if self.multiplier <= 0:
            raise ValueError(f"multiplier must be positive, got {self.multiplier}")
        if self.sizing_mode not in ("conviction", "proportional"):
            raise ValueError(
                f"sizing_mode must be 'conviction' or 'proportional', "
                f"got {self.sizing_mode!r}"
            )
        if self.min_history < 10:
            raise ValueError(f"min_history must be >= 10, got {self.min_history}")
        if not 0 <= self.cold_start_pct <= 100:
            raise ValueError(f"cold_start_pct must be 0-100, got {self.cold_start_pct}")
        if not 0 < self.trade_size_pct <= 100:
            raise ValueError(f"trade_size_pct must be 0-100, got {self.trade_size_pct}")
        if self.aggregation_seconds < 0:
            raise ValueError(
                f"aggregation_seconds must be >= 0, got {self.aggregation_seconds}"
            )
