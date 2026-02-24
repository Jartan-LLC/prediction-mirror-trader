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
    label="Whale", platform="polymarket", address="0xAAA", allocation_pct=50.0,
    sizing_mode="proportional",
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
        result, reason, _ = size_order(
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
        result, _, _ = size_order(
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
        result, reason, _ = size_order(
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
        result, _, _ = size_order(
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
        result, _, _ = size_order(
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
        result, reason, _ = size_order(
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
            allocation_pct=50.0, multiplier=2.0, sizing_mode="proportional",
        )
        sig = _signal(target=target, delta=10.0, price=0.55)
        result, _, _ = size_order(
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
        result, reason, _ = size_order(
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
        result, _, _ = size_order(
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
        result, _, _ = size_order(
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
        result, reason, _ = size_order(
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
        result, reason, _ = size_order(
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
        result, reason, _ = size_order(
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
        result, reason, _ = size_order(
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


# ── Percentile Rank ──


class TestPercentileRank:
    def test_lowest_value(self):
        from prediction_mirror.engine.strategy import percentile_rank

        assert percentile_rank(1.0, [1.0, 2.0, 3.0, 4.0, 5.0]) == pytest.approx(0.2)

    def test_highest_value(self):
        from prediction_mirror.engine.strategy import percentile_rank

        assert percentile_rank(5.0, [1.0, 2.0, 3.0, 4.0, 5.0]) == pytest.approx(1.0)

    def test_median_value(self):
        from prediction_mirror.engine.strategy import percentile_rank

        assert percentile_rank(3.0, [1.0, 2.0, 3.0, 4.0, 5.0]) == pytest.approx(0.6)

    def test_above_all(self):
        from prediction_mirror.engine.strategy import percentile_rank

        assert percentile_rank(10.0, [1.0, 2.0, 3.0]) == pytest.approx(1.0)

    def test_below_all(self):
        from prediction_mirror.engine.strategy import percentile_rank

        assert percentile_rank(0.5, [1.0, 2.0, 3.0]) == pytest.approx(0.0)


# ── Conviction Sizing ──


CONVICTION_TARGET = TargetConfig(
    label="Whale", platform="polymarket", address="0xAAA",
    allocation_pct=50.0, sizing_mode="conviction",
    min_history=10, cold_start_pct=50.0, trade_size_pct=1.0,
)


class TestConvictionSizing:
    def test_cold_start_uses_fixed_fraction(self):
        from prediction_mirror.engine.strategy import size_order

        sig = _signal(target=CONVICTION_TARGET, delta=100.0, price=0.50)
        # Only 5 trades in history — below min_history of 10
        history = [10.0, 20.0, 30.0, 40.0, 50.0]
        result, reason, _ = size_order(
            signal=sig, current_price=0.50, portfolio_value=1000.0,
            target_portfolio_value=0, deployed_for_target=0.0,
            our_position=None, settings=Settings(min_order_usd=0.01),
            trade_history=history,
        )
        assert result is not None
        assert reason is None
        # budget = 500, cold_start = 50% → $250
        assert result.usd_amount == pytest.approx(250.0)

    def test_conviction_low_percentile(self):
        from prediction_mirror.engine.strategy import size_order

        sig = _signal(target=CONVICTION_TARGET, delta=10.0, price=0.50)
        # 10 trades: this trade (10*0.50=$5) is very small
        history = [5.0, 10.0, 20.0, 50.0, 100.0, 200.0, 300.0, 400.0, 500.0, 1000.0]
        result, _, _ = size_order(
            signal=sig, current_price=0.50, portfolio_value=1000.0,
            target_portfolio_value=0, deployed_for_target=0.0,
            our_position=None, settings=Settings(min_order_usd=0.01),
            trade_history=history,
        )
        assert result is not None
        # trade_usd = $5, P10. fraction = 1% * (1 + 0.1) = 1.1%
        # usd = 500 * 0.011 = $5.50
        assert result.usd_amount == pytest.approx(5.50)

    def test_conviction_high_percentile(self):
        from prediction_mirror.engine.strategy import size_order

        sig = _signal(target=CONVICTION_TARGET, delta=2000.0, price=0.50)
        # trade_usd = $1000, above everything in history → P100
        history = [5.0, 10.0, 20.0, 50.0, 100.0, 200.0, 300.0, 400.0, 500.0, 800.0]
        result, _, _ = size_order(
            signal=sig, current_price=0.50, portfolio_value=1000.0,
            target_portfolio_value=0, deployed_for_target=0.0,
            our_position=None, settings=Settings(min_order_usd=0.01),
            trade_history=history,
        )
        assert result is not None
        # P100. fraction = 1% * (1 + 1.0) = 2% → usd = 500 * 0.02 = $10
        assert result.usd_amount == pytest.approx(10.0)

    def test_conviction_minimum_at_p0(self):
        from prediction_mirror.engine.strategy import size_order

        sig = _signal(target=CONVICTION_TARGET, delta=1.0, price=0.50)
        # trade_usd=$0.50, below everything → P0
        history = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
        result, _, _ = size_order(
            signal=sig, current_price=0.50, portfolio_value=1000.0,
            target_portfolio_value=0, deployed_for_target=0.0,
            our_position=None, settings=Settings(min_order_usd=0.01),
            trade_history=history,
        )
        assert result is not None
        # P0. fraction = 1% * (1 + 0) = 1% → usd = 500 * 0.01 = $5
        assert result.usd_amount == pytest.approx(5.0)

    def test_conviction_empty_history_uses_cold_start(self):
        from prediction_mirror.engine.strategy import size_order

        sig = _signal(target=CONVICTION_TARGET, delta=100.0, price=0.50)
        result, _, _ = size_order(
            signal=sig, current_price=0.50, portfolio_value=1000.0,
            target_portfolio_value=0, deployed_for_target=0.0,
            our_position=None, settings=Settings(min_order_usd=0.01),
            trade_history=[],
        )
        assert result is not None
        assert result.usd_amount == pytest.approx(250.0)

    def test_higher_trade_size_pct(self):
        from prediction_mirror.engine.strategy import size_order

        target = TargetConfig(
            label="Whale", platform="polymarket", address="0xAAA",
            allocation_pct=50.0, sizing_mode="conviction",
            trade_size_pct=5.0,  # 5% base
        )
        sig = _signal(target=target, delta=100.0, price=0.50)
        # P100 → fraction = 5% * (1 + 1.0) = 10%
        history = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        result, _, _ = size_order(
            signal=sig, current_price=0.50, portfolio_value=1000.0,
            target_portfolio_value=0, deployed_for_target=0.0,
            our_position=None, settings=Settings(min_order_usd=0.01),
            trade_history=history,
        )
        assert result is not None
        # 500 * 0.10 = $50
        assert result.usd_amount == pytest.approx(50.0)

    def test_proportional_mode_still_works(self):
        from prediction_mirror.engine.strategy import size_order

        prop_target = TargetConfig(
            label="Whale", platform="polymarket", address="0xAAA",
            allocation_pct=50.0, sizing_mode="proportional",
        )
        sig = _signal(target=prop_target, delta=100.0, price=0.55)
        result, _, _ = size_order(
            signal=sig, current_price=0.55, portfolio_value=1000.0,
            target_portfolio_value=5000.0, deployed_for_target=0.0,
            our_position=None, settings=Settings(min_order_usd=0.01),
        )
        assert result is not None
        # ratio = 500/5000 = 0.1, raw = 100*0.1 = 10, usd = 5.50
        assert result.usd_amount == pytest.approx(5.50)

    def test_multiplier_applied_in_conviction(self):
        from prediction_mirror.engine.strategy import size_order

        target = TargetConfig(
            label="Whale", platform="polymarket", address="0xAAA",
            allocation_pct=50.0, sizing_mode="conviction", multiplier=2.0,
            cold_start_pct=50.0,
        )
        sig = _signal(target=target, delta=100.0, price=0.50)
        result, _, _ = size_order(
            signal=sig, current_price=0.50, portfolio_value=1000.0,
            target_portfolio_value=0, deployed_for_target=0.0,
            our_position=None, settings=Settings(min_order_usd=0.01, max_order_usd=10000.0),
            trade_history=[],
        )
        assert result is not None
        # cold start 50% of $500 = $250, * 2.0 multiplier = $500
        assert result.usd_amount == pytest.approx(500.0)
