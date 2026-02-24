from __future__ import annotations

from datetime import datetime, timezone

import pytest

from prediction_mirror.models import (
    Market,
    MarketStatus,
    OrderResult,
    OrderSide,
    OurPosition,
    Settings,
    Signal,
    SignalType,
    SizedOrder,
    TargetConfig,
    TargetPosition,
    WalletState,
)

NOW = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


# ── TargetConfig ──


class TestTargetConfig:
    def test_construction(self, target_config: TargetConfig):
        assert target_config.label == "Whale Alpha"
        assert target_config.platform == "polymarket"
        assert target_config.allocation_pct == 50.0
        assert target_config.multiplier == 1.0
        assert target_config.enabled is True

    def test_defaults(self):
        t = TargetConfig(label="Test", platform="poly", address="0x123", allocation_pct=25.0)
        assert t.multiplier == 1.0
        assert t.enabled is True

    def test_custom_multiplier(self):
        t = TargetConfig(
            label="Test", platform="poly", address="0x123", allocation_pct=30.0, multiplier=2.0
        )
        assert t.multiplier == 2.0

    def test_empty_label_raises(self):
        with pytest.raises(ValueError, match="label must not be empty"):
            TargetConfig(label="", platform="poly", address="0x123", allocation_pct=10.0)

    def test_negative_allocation_raises(self):
        with pytest.raises(ValueError, match="allocation_pct must be 0-100"):
            TargetConfig(label="Bad", platform="poly", address="0x123", allocation_pct=-5.0)

    def test_over_100_allocation_raises(self):
        with pytest.raises(ValueError, match="allocation_pct must be 0-100"):
            TargetConfig(label="Bad", platform="poly", address="0x123", allocation_pct=101.0)

    def test_zero_multiplier_raises(self):
        with pytest.raises(ValueError, match="multiplier must be positive"):
            TargetConfig(
                label="Bad", platform="poly", address="0x123", allocation_pct=10.0, multiplier=0
            )

    def test_negative_multiplier_raises(self):
        with pytest.raises(ValueError, match="multiplier must be positive"):
            TargetConfig(
                label="Bad", platform="poly", address="0x123", allocation_pct=10.0, multiplier=-1.0
            )

    def test_zero_allocation_valid(self):
        t = TargetConfig(label="Paused", platform="poly", address="0x123", allocation_pct=0.0)
        assert t.allocation_pct == 0.0

    def test_100_allocation_valid(self):
        t = TargetConfig(label="All In", platform="poly", address="0x123", allocation_pct=100.0)
        assert t.allocation_pct == 100.0


# ── Market ──


class TestMarket:
    def test_construction(self, market: Market):
        assert market.market_id == "condition_abc123"
        assert market.status == MarketStatus.OPEN
        assert market.outcomes == ["Yes", "No"]
        assert market.resolution_outcome is None

    def test_resolved_market(self):
        m = Market(
            market_id="cond_456",
            platform="polymarket",
            question="Resolved?",
            outcomes=["Yes", "No"],
            status=MarketStatus.RESOLVED,
            resolution_outcome="Yes",
        )
        assert m.status == MarketStatus.RESOLVED
        assert m.resolution_outcome == "Yes"

    def test_market_status_values(self):
        assert MarketStatus.OPEN.value == "OPEN"
        assert MarketStatus.RESOLVED.value == "RESOLVED"
        assert MarketStatus.CLOSED.value == "CLOSED"


# ── TargetPosition ──


class TestTargetPosition:
    def test_construction(self, target_position: TargetPosition):
        assert target_position.size == 100.0
        assert target_position.avg_price == 0.55
        assert target_position.current_price == 0.60
        assert target_position.outcome == "Yes"


# ── OurPosition ──


class TestOurPosition:
    def test_construction(self, our_position: OurPosition):
        assert our_position.size == 15.0
        assert our_position.avg_entry_price == 0.52
        assert our_position.total_cost == 7.80
        assert our_position.realized_pnl == 0.0
        assert our_position.source_target == "Whale Alpha"
        assert our_position.dry_run is True


# ── Signal ──


class TestSignal:
    def test_construction(self, signal: Signal):
        assert signal.signal_type == SignalType.BUY
        assert signal.target.label == "Whale Alpha"
        assert signal.target_delta == 10.0
        assert signal.target_prev_size == 90.0

    def test_signal_type_values(self):
        assert SignalType.BUY.value == "BUY"
        assert SignalType.SELL.value == "SELL"

    def test_sell_signal(self, target_config: TargetConfig):
        s = Signal(
            signal_type=SignalType.SELL,
            target=target_config,
            platform="polymarket",
            market_id="cond_1",
            asset_id="tok_1",
            outcome="No",
            target_delta=5.0,
            target_prev_size=20.0,
            target_price=0.40,
            detected_at=NOW,
        )
        assert s.signal_type == SignalType.SELL
        assert s.target_delta == 5.0


# ── SizedOrder ──


class TestSizedOrder:
    def test_construction(self, sized_order: SizedOrder):
        assert sized_order.side == OrderSide.BUY
        assert sized_order.size == 5.0
        assert sized_order.usd_amount == 2.75
        assert sized_order.dry_run is True

    def test_order_side_values(self):
        assert OrderSide.BUY.value == "BUY"
        assert OrderSide.SELL.value == "SELL"


# ── OrderResult ──


class TestOrderResult:
    def test_successful_result(self, order_result: OrderResult):
        assert order_result.success is True
        assert order_result.order_id == "ord_12345"
        assert order_result.fill_price == 0.55
        assert order_result.fill_size == 5.0
        assert order_result.error is None

    def test_failed_result(self, sized_order: SizedOrder):
        r = OrderResult(
            order=sized_order,
            success=False,
            order_id=None,
            fill_price=None,
            fill_size=None,
            error="Insufficient funds",
            executed_at=NOW,
        )
        assert r.success is False
        assert r.error == "Insufficient funds"
        assert r.order_id is None


# ── WalletState ──


class TestWalletState:
    def test_construction(self, wallet_state: WalletState):
        assert wallet_state.total_balance == 1000.0
        assert wallet_state.gas_balance == 0.5
        assert wallet_state.approvals_ok is True

    def test_no_gas_balance(self):
        w = WalletState(platform="kalshi", total_balance=500.0, gas_balance=None, approvals_ok=True)
        assert w.gas_balance is None


# ── Settings ──


class TestSettings:
    def test_defaults(self, settings: Settings):
        assert settings.poll_interval_seconds == 2
        assert settings.slippage_tolerance_pct == 2.0
        assert settings.min_order_usd == 1.0
        assert settings.max_order_usd == 500.0
        assert settings.max_position_usd == 1000.0
        assert settings.aggregation_window_seconds == 0
        assert settings.redeemer_interval_seconds == 7200
        assert settings.dashboard_refresh_seconds == 30
        assert settings.dry_run is True
        assert settings.log_level == "INFO"

    def test_custom_settings(self):
        s = Settings(poll_interval_seconds=5, dry_run=False, max_order_usd=100.0)
        assert s.poll_interval_seconds == 5
        assert s.dry_run is False
        assert s.max_order_usd == 100.0

    def test_poll_interval_too_low_raises(self):
        with pytest.raises(ValueError, match="poll_interval_seconds must be >= 1"):
            Settings(poll_interval_seconds=0)

    def test_negative_min_order_raises(self):
        with pytest.raises(ValueError, match="min_order_usd must be >= 0"):
            Settings(min_order_usd=-1.0)

    def test_max_less_than_min_raises(self):
        with pytest.raises(ValueError, match="max_order_usd.*must be >= min_order_usd"):
            Settings(min_order_usd=100.0, max_order_usd=50.0)

    def test_negative_max_position_raises(self):
        with pytest.raises(ValueError, match="max_position_usd must be >= 0"):
            Settings(max_position_usd=-10.0)


# ── Re-exports ──


class TestReExports:
    """Verify models/__init__.py re-exports all types."""

    def test_all_models_importable(self):
        from prediction_mirror.models import (
            Market,
            MarketStatus,
            OrderResult,
            OrderSide,
            OurPosition,
            Settings,
            Signal,
            SignalType,
            SizedOrder,
            TargetConfig,
            TargetPosition,
            WalletState,
        )

        # Just verify they're all classes/types
        assert all(
            callable(cls)
            for cls in [
                Market,
                MarketStatus,
                OrderResult,
                OrderSide,
                OurPosition,
                Settings,
                Signal,
                SignalType,
                SizedOrder,
                TargetConfig,
                TargetPosition,
                WalletState,
            ]
        )
