from __future__ import annotations

import pytest

from prediction_mirror.models.signal import SignalType
from prediction_mirror.models.target import TargetConfig

TARGET = TargetConfig(
    label="Whale", platform="polymarket", address="0xAAA", allocation_pct=50.0
)


class TestActivityToSignals:
    """Test conversion of raw activity trades to merged signals."""

    def test_single_buy(self):
        from prediction_mirror.engine.monitor import _activity_to_signals

        trades = [
            {"side": "BUY", "size": 100, "price": 0.50, "usdcSize": 50,
             "conditionId": "cond_1", "asset": "tok_1", "outcome": "Yes",
             "timestamp": 1000},
        ]
        signals = _activity_to_signals(trades, TARGET)
        assert len(signals) == 1
        assert signals[0].signal_type == SignalType.BUY
        assert signals[0].target_delta == 100
        assert signals[0].target_price == 0.50

    def test_single_sell(self):
        from prediction_mirror.engine.monitor import _activity_to_signals

        trades = [
            {"side": "SELL", "size": 50, "price": 0.60, "usdcSize": 30,
             "conditionId": "cond_1", "asset": "tok_1", "outcome": "Yes",
             "timestamp": 1000},
        ]
        signals = _activity_to_signals(trades, TARGET)
        assert len(signals) == 1
        assert signals[0].signal_type == SignalType.SELL
        assert signals[0].target_delta == 50

    def test_merge_fragments_same_market(self):
        from prediction_mirror.engine.monitor import _activity_to_signals

        trades = [
            {"side": "BUY", "size": 200, "price": 0.50, "usdcSize": 100,
             "conditionId": "cond_1", "asset": "tok_1", "outcome": "Yes",
             "timestamp": 1000},
            {"side": "BUY", "size": 150, "price": 0.52, "usdcSize": 78,
             "conditionId": "cond_1", "asset": "tok_1", "outcome": "Yes",
             "timestamp": 1001},
            {"side": "BUY", "size": 100, "price": 0.48, "usdcSize": 48,
             "conditionId": "cond_1", "asset": "tok_1", "outcome": "Yes",
             "timestamp": 1002},
        ]
        signals = _activity_to_signals(trades, TARGET)
        assert len(signals) == 1
        assert signals[0].target_delta == 450  # 200 + 150 + 100
        # VWAP = (100 + 78 + 48) / 450 = 0.5022...
        assert signals[0].target_price == pytest.approx(226 / 450, abs=0.001)

    def test_different_markets_not_merged(self):
        from prediction_mirror.engine.monitor import _activity_to_signals

        trades = [
            {"side": "BUY", "size": 100, "price": 0.50, "usdcSize": 50,
             "conditionId": "cond_1", "asset": "tok_1", "outcome": "Yes",
             "timestamp": 1000},
            {"side": "BUY", "size": 200, "price": 0.30, "usdcSize": 60,
             "conditionId": "cond_2", "asset": "tok_2", "outcome": "No",
             "timestamp": 1001},
        ]
        signals = _activity_to_signals(trades, TARGET)
        assert len(signals) == 2

    def test_buy_and_sell_same_market_not_merged(self):
        from prediction_mirror.engine.monitor import _activity_to_signals

        trades = [
            {"side": "BUY", "size": 100, "price": 0.50, "usdcSize": 50,
             "conditionId": "cond_1", "asset": "tok_1", "outcome": "Yes",
             "timestamp": 1000},
            {"side": "SELL", "size": 50, "price": 0.60, "usdcSize": 30,
             "conditionId": "cond_1", "asset": "tok_1", "outcome": "Yes",
             "timestamp": 1001},
        ]
        signals = _activity_to_signals(trades, TARGET)
        assert len(signals) == 2
        buy = [s for s in signals if s.signal_type == SignalType.BUY]
        sell = [s for s in signals if s.signal_type == SignalType.SELL]
        assert len(buy) == 1
        assert len(sell) == 1

    def test_empty_trades(self):
        from prediction_mirror.engine.monitor import _activity_to_signals

        signals = _activity_to_signals([], TARGET)
        assert signals == []

    def test_signal_carries_target(self):
        from prediction_mirror.engine.monitor import _activity_to_signals

        trades = [
            {"side": "BUY", "size": 10, "price": 0.50, "usdcSize": 5,
             "conditionId": "cond_1", "asset": "tok_1", "outcome": "Yes",
             "timestamp": 1000},
        ]
        signals = _activity_to_signals(trades, TARGET)
        assert signals[0].target.label == "Whale"
        assert signals[0].platform == "polymarket"

    def test_uses_latest_timestamp(self):
        from prediction_mirror.engine.monitor import _activity_to_signals

        trades = [
            {"side": "BUY", "size": 100, "price": 0.50, "usdcSize": 50,
             "conditionId": "cond_1", "asset": "tok_1", "outcome": "Yes",
             "timestamp": 1000},
            {"side": "BUY", "size": 100, "price": 0.50, "usdcSize": 50,
             "conditionId": "cond_1", "asset": "tok_1", "outcome": "Yes",
             "timestamp": 2000},
        ]
        signals = _activity_to_signals(trades, TARGET)
        assert signals[0].detected_at.timestamp() == 2000
