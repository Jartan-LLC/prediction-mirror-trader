from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Settings:
    poll_interval_seconds: int = 2
    slippage_tolerance_pct: float = 2.0
    min_order_usd: float = 1.0
    max_order_usd: float = 500.0
    max_position_usd: float = 1000.0
    aggregation_window_seconds: int = 0
    redeemer_interval_seconds: int = 7200
    dashboard_refresh_seconds: int = 30
    dry_run: bool = True
    dry_run_balance_usd: float = 1000.0
    dry_run_cash: float = -1.0  # -1 means "not initialized, use dry_run_balance_usd"
    log_level: str = "INFO"

    def __post_init__(self):
        if self.poll_interval_seconds < 1:
            raise ValueError(f"poll_interval_seconds must be >= 1, got {self.poll_interval_seconds}")
        if self.min_order_usd < 0:
            raise ValueError(f"min_order_usd must be >= 0, got {self.min_order_usd}")
        if self.max_order_usd < self.min_order_usd:
            raise ValueError(
                f"max_order_usd ({self.max_order_usd}) must be >= min_order_usd ({self.min_order_usd})"
            )
        if self.max_position_usd < 0:
            raise ValueError(f"max_position_usd must be >= 0, got {self.max_position_usd}")
