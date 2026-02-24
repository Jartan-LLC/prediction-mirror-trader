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


@pytest.fixture
def target_config() -> TargetConfig:
    return TargetConfig(
        label="Whale Alpha",
        platform="polymarket",
        address="0xABCDEF1234567890abcdef1234567890ABCDEF12",
        allocation_pct=50.0,
    )


@pytest.fixture
def market() -> Market:
    return Market(
        market_id="condition_abc123",
        platform="polymarket",
        question="Will BTC exceed $100k by end of 2025?",
        outcomes=["Yes", "No"],
        status=MarketStatus.OPEN,
    )


@pytest.fixture
def target_position() -> TargetPosition:
    return TargetPosition(
        target_address="0xABCDEF1234567890abcdef1234567890ABCDEF12",
        platform="polymarket",
        market_id="condition_abc123",
        asset_id="token_yes_001",
        outcome="Yes",
        size=100.0,
        avg_price=0.55,
        current_price=0.60,
        snapshot_time=NOW,
    )


@pytest.fixture
def our_position() -> OurPosition:
    return OurPosition(
        market_id="condition_abc123",
        asset_id="token_yes_001",
        platform="polymarket",
        outcome="Yes",
        size=15.0,
        avg_entry_price=0.52,
        total_cost=7.80,
        realized_pnl=0.0,
        source_target="Whale Alpha",
        dry_run=True,
        updated_at=NOW,
    )


@pytest.fixture
def signal(target_config: TargetConfig) -> Signal:
    return Signal(
        signal_type=SignalType.BUY,
        target=target_config,
        platform="polymarket",
        market_id="condition_abc123",
        asset_id="token_yes_001",
        outcome="Yes",
        target_delta=10.0,
        target_prev_size=90.0,
        target_price=0.55,
        detected_at=NOW,
    )


@pytest.fixture
def sized_order(signal: Signal) -> SizedOrder:
    return SizedOrder(
        signal=signal,
        side=OrderSide.BUY,
        asset_id="token_yes_001",
        price=0.55,
        size=5.0,
        usd_amount=2.75,
        dry_run=True,
    )


@pytest.fixture
def order_result(sized_order: SizedOrder) -> OrderResult:
    return OrderResult(
        order=sized_order,
        success=True,
        order_id="ord_12345",
        fill_price=0.55,
        fill_size=5.0,
        error=None,
        executed_at=NOW,
    )


@pytest.fixture
def wallet_state() -> WalletState:
    return WalletState(
        platform="polymarket",
        total_balance=1000.0,
        gas_balance=0.5,
        approvals_ok=True,
    )


@pytest.fixture
def settings() -> Settings:
    return Settings()
