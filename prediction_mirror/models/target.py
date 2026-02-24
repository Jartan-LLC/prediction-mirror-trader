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
    cold_start_pct: float = 50.0
    conviction_floor_pct: float = 10.0
    conviction_ceiling_pct: float = 90.0

    def __post_init__(self):
        if not self.label:
            raise ValueError("label must not be empty")
        if self.allocation_pct < 0 or self.allocation_pct > 100:
            raise ValueError(f"allocation_pct must be 0-100, got {self.allocation_pct}")
        if self.multiplier <= 0:
            raise ValueError(f"multiplier must be positive, got {self.multiplier}")
        if self.sizing_mode not in ("conviction", "proportional"):
            raise ValueError(f"sizing_mode must be 'conviction' or 'proportional', got {self.sizing_mode!r}")
        if self.min_history < 10:
            raise ValueError(f"min_history must be >= 10, got {self.min_history}")
        if not 1 <= self.cold_start_pct <= 100:
            raise ValueError(f"cold_start_pct must be 1-100, got {self.cold_start_pct}")
        if not 1 <= self.conviction_floor_pct <= 100:
            raise ValueError(f"conviction_floor_pct must be 1-100, got {self.conviction_floor_pct}")
        if not 1 <= self.conviction_ceiling_pct <= 100:
            raise ValueError(f"conviction_ceiling_pct must be 1-100, got {self.conviction_ceiling_pct}")
        if self.conviction_floor_pct >= self.conviction_ceiling_pct:
            raise ValueError(
                f"conviction_floor_pct ({self.conviction_floor_pct}) must be < "
                f"conviction_ceiling_pct ({self.conviction_ceiling_pct})"
            )
