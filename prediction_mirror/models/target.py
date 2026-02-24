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

    def __post_init__(self):
        if not self.label:
            raise ValueError("label must not be empty")
        if self.allocation_pct < 0 or self.allocation_pct > 100:
            raise ValueError(f"allocation_pct must be 0-100, got {self.allocation_pct}")
        if self.multiplier <= 0:
            raise ValueError(f"multiplier must be positive, got {self.multiplier}")
