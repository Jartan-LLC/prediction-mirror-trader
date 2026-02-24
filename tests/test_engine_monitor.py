from __future__ import annotations

from datetime import datetime, timezone

import pytest

from prediction_mirror.models.position import TargetPosition
from prediction_mirror.models.signal import SignalType
from prediction_mirror.models.target import TargetConfig

NOW = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

TARGET = TargetConfig(
    label="Whale", platform="polymarket", address="0xAAA", allocation_pct=50.0
)


def _pos(market_id="c1", asset_id="t1", outcome="Yes", size=100.0, price=0.55):
    return TargetPosition(
        target_address="0xAAA",
        platform="polymarket",
        market_id=market_id,
        asset_id=asset_id,
        outcome=outcome,
        size=size,
        avg_price=price,
        current_price=price,
        snapshot_time=NOW,
    )


class TestDiffPositions:
    """Pure function tests for diff_positions. No I/O."""

    def test_new_position_generates_buy(self):
        from prediction_mirror.engine.monitor import diff_positions

        old: list[TargetPosition] = []
        new = [_pos(size=100.0)]
        signals = diff_positions(old, new, TARGET)
        assert len(signals) == 1
        assert signals[0].signal_type == SignalType.BUY
        assert signals[0].target_delta == 100.0
        assert signals[0].target_prev_size == 0.0

    def test_increased_position_generates_buy(self):
        from prediction_mirror.engine.monitor import diff_positions

        old = [_pos(size=100.0)]
        new = [_pos(size=150.0)]
        signals = diff_positions(old, new, TARGET)
        assert len(signals) == 1
        assert signals[0].signal_type == SignalType.BUY
        assert signals[0].target_delta == 50.0
        assert signals[0].target_prev_size == 100.0

    def test_decreased_position_generates_sell(self):
        from prediction_mirror.engine.monitor import diff_positions

        old = [_pos(size=100.0)]
        new = [_pos(size=60.0)]
        signals = diff_positions(old, new, TARGET)
        assert len(signals) == 1
        assert signals[0].signal_type == SignalType.SELL
        assert signals[0].target_delta == 40.0
        assert signals[0].target_prev_size == 100.0

    def test_full_exit_generates_sell(self):
        from prediction_mirror.engine.monitor import diff_positions

        old = [_pos(size=100.0)]
        new: list[TargetPosition] = []  # position gone
        signals = diff_positions(old, new, TARGET)
        assert len(signals) == 1
        assert signals[0].signal_type == SignalType.SELL
        assert signals[0].target_delta == 100.0
        assert signals[0].target_prev_size == 100.0

    def test_no_change_no_signal(self):
        from prediction_mirror.engine.monitor import diff_positions

        old = [_pos(size=100.0)]
        new = [_pos(size=100.0)]
        signals = diff_positions(old, new, TARGET)
        assert len(signals) == 0

    def test_dust_threshold_filters_small_changes(self):
        from prediction_mirror.engine.monitor import diff_positions

        old = [_pos(size=100.0)]
        new = [_pos(size=100.001)]  # tiny increase
        signals = diff_positions(old, new, TARGET, dust_threshold=0.01)
        assert len(signals) == 0

    def test_multiple_positions_diffed(self):
        from prediction_mirror.engine.monitor import diff_positions

        old = [
            _pos(market_id="c1", asset_id="t1", size=100.0),
            _pos(market_id="c2", asset_id="t2", size=50.0),
        ]
        new = [
            _pos(market_id="c1", asset_id="t1", size=120.0),  # increased
            _pos(market_id="c2", asset_id="t2", size=30.0),   # decreased
        ]
        signals = diff_positions(old, new, TARGET)
        assert len(signals) == 2
        buy = [s for s in signals if s.signal_type == SignalType.BUY]
        sell = [s for s in signals if s.signal_type == SignalType.SELL]
        assert len(buy) == 1
        assert len(sell) == 1
        assert buy[0].target_delta == 20.0
        assert sell[0].target_delta == 20.0

    def test_signal_carries_target_config(self):
        from prediction_mirror.engine.monitor import diff_positions

        old: list[TargetPosition] = []
        new = [_pos(size=10.0)]
        signals = diff_positions(old, new, TARGET)
        assert signals[0].target.label == "Whale"
        assert signals[0].target.allocation_pct == 50.0

    def test_signal_carries_price(self):
        from prediction_mirror.engine.monitor import diff_positions

        old: list[TargetPosition] = []
        new = [_pos(size=10.0, price=0.72)]
        signals = diff_positions(old, new, TARGET)
        assert signals[0].target_price == 0.72
