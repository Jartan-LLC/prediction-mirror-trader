from __future__ import annotations

from datetime import datetime, timezone

import pytest

from prediction_mirror.models.order import OrderSide
from prediction_mirror.models.position import OurPosition
from prediction_mirror.models.settings import Settings
from prediction_mirror.models.signal import Signal, SignalType
from prediction_mirror.models.target import TargetConfig

NOW = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

TARGET = TargetConfig(
    label="Whale", platform="polymarket", address="0xAAA", allocation_pct=50.0
)


def _signal(
    signal_type=SignalType.BUY,
    target=TARGET,
    delta=10.0,
    prev_size=90.0,
    price=0.55,
):
    return Signal(
        signal_type=signal_type,
        target=target,
        platform="polymarket",
        market_id="cond_1",
        asset_id="tok_1",
        outcome="Yes",
        target_delta=delta,
        target_prev_size=prev_size,
        target_price=price,
        detected_at=NOW,
    )


def _position(size=15.0, avg_entry=0.52, dry_run=False):
    return OurPosition(
        market_id="cond_1",
        asset_id="tok_1",
        platform="polymarket",
        outcome="Yes",
        size=size,
        avg_entry_price=avg_entry,
        total_cost=size * avg_entry,
        realized_pnl=0.0,
        source_target="Whale",
        dry_run=dry_run,
        updated_at=NOW,
    )


class TestSizeOrderBuy:
    """Buy sizing: scale target's delta relative to our budget."""

    def test_basic_buy(self):
        from prediction_mirror.engine.strategy import size_order

        sig = _signal(delta=100.0, price=0.55)
        result, reason = size_order(
            signal=sig,
            current_price=0.55,
            portfolio_value=1000.0,
            target_portfolio_value=5000.0,
            deployed_for_target=0.0,
            our_position=None,
            settings=Settings(min_order_usd=0.01),
        )
        assert result is not None
        assert reason is None
        assert result.side == OrderSide.BUY
        assert result.size == pytest.approx(10.0)
        assert result.usd_amount == pytest.approx(5.50)

    def test_buy_respects_available_budget(self):
        from prediction_mirror.engine.strategy import size_order

        sig = _signal(delta=100.0, price=0.55)
        result, _ = size_order(
            signal=sig,
            current_price=0.55,
            portfolio_value=1000.0,
            target_portfolio_value=500.0,
            deployed_for_target=400.0,
            our_position=None,
            settings=Settings(),
        )
        assert result is not None
        assert result.usd_amount <= 100.0

    def test_buy_returns_none_when_no_budget(self):
        from prediction_mirror.engine.strategy import size_order

        sig = _signal(delta=10.0, price=0.55)
        result, reason = size_order(
            signal=sig,
            current_price=0.55,
            portfolio_value=1000.0,
            target_portfolio_value=5000.0,
            deployed_for_target=500.0,
            our_position=None,
            settings=Settings(),
        )
        assert result is None
        assert "no budget" in reason

    def test_buy_respects_max_order_usd(self):
        from prediction_mirror.engine.strategy import size_order

        sig = _signal(delta=1000.0, price=0.55)
        settings = Settings(max_order_usd=10.0)
        result, _ = size_order(
            signal=sig,
            current_price=0.55,
            portfolio_value=100000.0,
            target_portfolio_value=5000.0,
            deployed_for_target=0.0,
            our_position=None,
            settings=settings,
        )
        assert result is not None
        assert result.usd_amount <= 10.0

    def test_buy_respects_max_position_usd(self):
        from prediction_mirror.engine.strategy import size_order

        sig = _signal(delta=1000.0, price=0.55)
        settings = Settings(max_position_usd=20.0)
        existing = _position(size=30.0, avg_entry=0.50)
        result, _ = size_order(
            signal=sig,
            current_price=0.55,
            portfolio_value=100000.0,
            target_portfolio_value=5000.0,
            deployed_for_target=0.0,
            our_position=existing,
            settings=settings,
        )
        assert result is not None
        assert result.usd_amount <= 5.01

    def test_buy_skipped_below_min_order(self):
        from prediction_mirror.engine.strategy import size_order

        sig = _signal(delta=0.1, price=0.55)
        settings = Settings(min_order_usd=5.0)
        result, reason = size_order(
            signal=sig,
            current_price=0.55,
            portfolio_value=1000.0,
            target_portfolio_value=5000.0,
            deployed_for_target=0.0,
            our_position=None,
            settings=settings,
        )
        assert result is None
        assert "below minimum" in reason

    def test_buy_with_multiplier(self):
        from prediction_mirror.engine.strategy import size_order

        target = TargetConfig(
            label="Whale", platform="polymarket", address="0xAAA",
            allocation_pct=50.0, multiplier=2.0,
        )
        sig = _signal(target=target, delta=10.0, price=0.55)
        result, _ = size_order(
            signal=sig,
            current_price=0.55,
            portfolio_value=1000.0,
            target_portfolio_value=5000.0,
            deployed_for_target=0.0,
            our_position=None,
            settings=Settings(),
        )
        assert result is not None
        assert result.size == pytest.approx(2.0)

    def test_buy_slippage_exceeded(self):
        from prediction_mirror.engine.strategy import size_order

        sig = _signal(delta=100.0, price=0.50)
        result, reason = size_order(
            signal=sig,
            current_price=0.60,  # 20% slippage
            portfolio_value=1000.0,
            target_portfolio_value=5000.0,
            deployed_for_target=0.0,
            our_position=None,
            settings=Settings(slippage_tolerance_pct=2.0, min_order_usd=0.01),
        )
        assert result is None
        assert "slippage" in reason


class TestSizeOrderSell:
    """Sell sizing: mirror target's percentage reduction."""

    def test_basic_sell(self):
        from prediction_mirror.engine.strategy import size_order

        sig = _signal(signal_type=SignalType.SELL, delta=20.0, prev_size=100.0, price=0.55)
        existing = _position(size=10.0)
        result, _ = size_order(
            signal=sig,
            current_price=0.55,
            portfolio_value=1000.0,
            target_portfolio_value=5000.0,
            deployed_for_target=100.0,
            our_position=existing,
            settings=Settings(),
        )
        assert result is not None
        assert result.side == OrderSide.SELL
        assert result.size == pytest.approx(2.0)

    def test_full_exit_sells_everything(self):
        from prediction_mirror.engine.strategy import size_order

        sig = _signal(signal_type=SignalType.SELL, delta=100.0, prev_size=100.0, price=0.55)
        existing = _position(size=10.0)
        result, _ = size_order(
            signal=sig,
            current_price=0.55,
            portfolio_value=1000.0,
            target_portfolio_value=5000.0,
            deployed_for_target=100.0,
            our_position=existing,
            settings=Settings(),
        )
        assert result is not None
        assert result.size == pytest.approx(10.0)

    def test_sell_returns_none_without_position(self):
        from prediction_mirror.engine.strategy import size_order

        sig = _signal(signal_type=SignalType.SELL, delta=10.0, prev_size=100.0)
        result, reason = size_order(
            signal=sig,
            current_price=0.55,
            portfolio_value=1000.0,
            target_portfolio_value=5000.0,
            deployed_for_target=0.0,
            our_position=None,
            settings=Settings(),
        )
        assert result is None
        assert "no position" in reason

    def test_sell_returns_none_with_zero_position(self):
        from prediction_mirror.engine.strategy import size_order

        sig = _signal(signal_type=SignalType.SELL, delta=10.0, prev_size=100.0)
        existing = _position(size=0.0)
        result, reason = size_order(
            signal=sig,
            current_price=0.55,
            portfolio_value=1000.0,
            target_portfolio_value=5000.0,
            deployed_for_target=0.0,
            our_position=existing,
            settings=Settings(),
        )
        assert result is None
        assert "no position" in reason

    def test_sell_skipped_below_min_order(self):
        from prediction_mirror.engine.strategy import size_order

        sig = _signal(signal_type=SignalType.SELL, delta=1.0, prev_size=100.0, price=0.55)
        existing = _position(size=0.5)
        result, reason = size_order(
            signal=sig,
            current_price=0.55,
            portfolio_value=1000.0,
            target_portfolio_value=5000.0,
            deployed_for_target=100.0,
            our_position=existing,
            settings=Settings(min_order_usd=1.0),
        )
        assert result is None
        assert "below minimum" in reason

    def test_sell_slippage_exceeded(self):
        from prediction_mirror.engine.strategy import size_order

        sig = _signal(signal_type=SignalType.SELL, delta=50.0, prev_size=100.0, price=0.50)
        existing = _position(size=10.0)
        result, reason = size_order(
            signal=sig,
            current_price=0.60,
            portfolio_value=1000.0,
            target_portfolio_value=5000.0,
            deployed_for_target=100.0,
            our_position=existing,
            settings=Settings(slippage_tolerance_pct=2.0),
        )
        assert result is None
        assert "slippage" in reason


class TestCheckSlippage:
    def test_acceptable(self):
        from prediction_mirror.engine.strategy import check_slippage

        assert check_slippage(1.00, 1.01, 2.0) is True

    def test_exceeded(self):
        from prediction_mirror.engine.strategy import check_slippage

        assert check_slippage(0.50, 0.55, 2.0) is False

    def test_zero_signal_price(self):
        from prediction_mirror.engine.strategy import check_slippage

        assert check_slippage(0.0, 0.55, 2.0) is True

    def test_within_tolerance(self):
        from prediction_mirror.engine.strategy import check_slippage

        assert check_slippage(1.00, 1.015, 2.0) is True

    def test_beyond_tolerance(self):
        from prediction_mirror.engine.strategy import check_slippage

        assert check_slippage(1.00, 1.03, 2.0) is False
