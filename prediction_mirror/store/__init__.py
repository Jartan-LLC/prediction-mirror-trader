from __future__ import annotations

import sqlite3

from prediction_mirror.models.order import OrderResult
from prediction_mirror.models.position import OurPosition, TargetPosition
from prediction_mirror.models.settings import Settings
from prediction_mirror.models.target import TargetConfig
from prediction_mirror.store import (
    portfolio,
    settings,
    signals,
    snapshots,
    targets,
    trade_history,
    trades,
)
from prediction_mirror.store.database import close, init_db


class Store:
    """Facade grouping all store modules with a shared connection."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # ── Settings ──

    def get_settings(self) -> Settings:
        return settings.get_current(self.conn)

    def get_setting(self, key: str) -> str:
        return settings.get_value(self.conn, key)

    def set_setting(self, key: str, value: str) -> None:
        settings.set_value(self.conn, key, value)

    def get_all_settings(self) -> list[tuple[str, str]]:
        return settings.get_all(self.conn)

    # ── Targets ──

    def add_target(self, target: TargetConfig) -> None:
        targets.add_target(self.conn, target)

    def get_enabled_targets(self) -> list[TargetConfig]:
        return targets.get_enabled(self.conn)

    def get_all_targets(self) -> list[TargetConfig]:
        return targets.get_all(self.conn)

    def get_target(self, label: str) -> TargetConfig | None:
        return targets.get_by_label(self.conn, label)

    def enable_target(self, label: str) -> None:
        targets.enable_target(self.conn, label)

    def disable_target(self, label: str) -> None:
        targets.disable_target(self.conn, label)

    def remove_target(self, label: str) -> None:
        targets.remove_target(self.conn, label)

    def set_allocation(self, label: str, pct: float) -> None:
        targets.set_allocation(self.conn, label, pct)

    # ── Snapshots ──

    def upsert_snapshot(self, pos: TargetPosition) -> None:
        snapshots.upsert_snapshot(self.conn, pos)

    def get_snapshot(
        self, target_address: str, platform: str, market_id: str, asset_id: str
    ) -> TargetPosition | None:
        return snapshots.get_snapshot(self.conn, target_address, platform, market_id, asset_id)

    def get_all_snapshots(self, target_address: str) -> list[TargetPosition]:
        return snapshots.get_all_snapshots(self.conn, target_address)

    # ── Signals ──

    def insert_signal(self, signal) -> int:
        return signals.insert_signal(self.conn, signal)

    def get_recent_signals(self, target_label: str, minutes: int = 60) -> list:
        return signals.get_recent_signals(self.conn, target_label, minutes)

    def get_signal_history(self, since=None, limit: int = 100) -> list:
        return signals.get_signal_history(self.conn, since, limit)

    # ── Trades ──

    def insert_trade(self, result: OrderResult, signal_id: int) -> int:
        return trades.insert_trade(self.conn, result, signal_id)

    def get_recent_trades(self, limit: int = 20) -> list:
        return trades.get_recent_trades(self.conn, limit)

    def get_trades_for_target(self, target_label: str, since=None) -> list:
        return trades.get_trades_for_target(self.conn, target_label, since)

    def get_trade_summary(self, dry_run: bool | None = None) -> dict:
        return trades.get_trade_summary(self.conn, dry_run)

    # ── Portfolio ──

    def upsert_position(self, pos: OurPosition) -> None:
        portfolio.upsert_position(self.conn, pos)

    def get_position(
        self, market_id: str, asset_id: str, source_target: str
    ) -> OurPosition | None:
        return portfolio.get_position(self.conn, market_id, asset_id, source_target)

    def get_all_positions(self, dry_run: bool | None = None) -> list[OurPosition]:
        return portfolio.get_all_positions(self.conn, dry_run)

    def get_positions_by_target(self, target_label: str) -> list[OurPosition]:
        return portfolio.get_positions_by_target(self.conn, target_label)

    def zero_out_position(
        self, market_id: str, asset_id: str, source_target: str
    ) -> None:
        portfolio.zero_out_position(self.conn, market_id, asset_id, source_target)

    def get_deployed_for_target(self, target_label: str) -> float:
        return portfolio.get_deployed_for_target(self.conn, target_label)

    def get_total_deployed(self) -> float:
        return portfolio.get_total_deployed(self.conn)

    def get_allocation_summary(self, targets: list, portfolio_value: float) -> dict:
        return portfolio.get_allocation_summary(self.conn, targets, portfolio_value)

    # ── Trade History ──

    def record_observed_trade(self, target_label: str, trade_usd: float, detected_at) -> None:
        trade_history.record_trade(self.conn, target_label, trade_usd, detected_at)

    def get_trade_history(self, target_label: str, limit: int = 50) -> list[float]:
        return trade_history.get_recent_trades(self.conn, target_label, limit)


__all__ = ["Store", "init_db", "close"]
