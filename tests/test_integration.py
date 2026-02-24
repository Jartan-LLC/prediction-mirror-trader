"""Integration test: full pipeline with mocked adapter over 3 poll ticks."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from prediction_mirror.dashboard.listener import DashboardListener
from prediction_mirror.engine.core import Engine
from prediction_mirror.models.market import Market, MarketStatus
from prediction_mirror.models.order import OrderResult, OrderSide
from prediction_mirror.models.position import TargetPosition
from prediction_mirror.models.target import TargetConfig
from prediction_mirror.models.wallet import WalletState
from prediction_mirror.store import Store, init_db

NOW = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
TARGET = TargetConfig(
    label="Whale", platform="polymarket", address="0xWhale", allocation_pct=50.0,
    cold_start_pct=50.0,
)


def _make_adapter(position_sequence: list[list[TargetPosition]]):
    """Create a mock adapter that returns different positions on each call."""
    adapter = AsyncMock()
    adapter.platform_name = "polymarket"

    call_count = 0

    async def _fetch_positions(address):
        nonlocal call_count
        idx = min(call_count, len(position_sequence) - 1)
        call_count += 1
        return position_sequence[idx]

    adapter.fetch_target_positions.side_effect = _fetch_positions
    adapter.fetch_target_portfolio_value.return_value = 5000.0
    adapter.get_wallet_state.return_value = WalletState(
        platform="polymarket", total_balance=1000.0, gas_balance=0.5, approvals_ok=True,
    )
    adapter.get_price.return_value = 0.55
    adapter.fetch_market.return_value = Market(
        market_id="cond_1", platform="polymarket", question="Test?",
        outcomes=["Yes", "No"], status=MarketStatus.OPEN,
    )

    async def _submit(order):
        return OrderResult(
            order=order, success=True, order_id="ord_123",
            fill_price=order.price, fill_size=order.size,
            error=None, executed_at=datetime.now(timezone.utc),
        )

    adapter.submit_order.side_effect = _submit
    adapter.initialize.return_value = None
    adapter.shutdown.return_value = None
    return adapter


def _pos(market_id="cond_1", asset_id="tok_yes", outcome="Yes", size=100.0, price=0.55):
    return TargetPosition(
        target_address="0xWhale", platform="polymarket",
        market_id=market_id, asset_id=asset_id, outcome=outcome,
        size=size, avg_price=price, current_price=price,
        snapshot_time=NOW,
    )


class TestFullPipeline:
    @pytest.mark.asyncio
    async def test_three_tick_pipeline(self):
        """Simulate: tick 1 = new position, tick 2 = increase, tick 3 = partial sell."""
        conn = init_db(":memory:")
        store = Store(conn)
        store.add_target(TARGET)
        store.set_setting("poll_interval_seconds", "1")
        store.set_setting("dry_run", "true")

        # Tick 1: target enters 100 shares
        # Tick 2: target increases to 150
        # Tick 3: target decreases to 100 (partial sell)
        positions_over_time = [
            [_pos(size=100.0)],
            [_pos(size=150.0)],
            [_pos(size=100.0)],
        ]

        adapter = _make_adapter(positions_over_time)
        engine = Engine(store, {"polymarket": adapter})
        dashboard = DashboardListener(store)
        engine.add_listener(dashboard)

        # Run engine for ~3 ticks then shutdown
        async def _run_and_stop():
            task = asyncio.create_task(engine.run())
            await asyncio.sleep(3.5)  # 3 ticks at 1s interval
            await engine.shutdown()
            await task

        await _run_and_stop()

        # Verify signals were generated
        signals = store.get_signal_history(limit=50)
        assert len(signals) >= 2  # at least BUY + one more

        # Verify trades were recorded
        trades = store.get_recent_trades(limit=50)
        assert len(trades) >= 1

        # Verify position exists
        pos = store.get_position("cond_1", "tok_yes", "Whale")
        assert pos is not None

        # Verify dashboard listener collected status
        assert dashboard.status in ("running", "stopped")

        conn.close()

    @pytest.mark.asyncio
    async def test_engine_survives_adapter_error(self):
        """Engine should not crash when adapter raises an error."""
        conn = init_db(":memory:")
        store = Store(conn)
        store.add_target(TARGET)
        store.set_setting("poll_interval_seconds", "1")

        adapter = AsyncMock()
        adapter.fetch_target_positions.side_effect = Exception("API down")
        adapter.shutdown.return_value = None

        engine = Engine(store, {"polymarket": adapter})
        errors = []

        class ErrorCollector:
            def on_error(self, error, context):
                errors.append(error)
            def on_signal(self, *a): pass
            def on_trade(self, *a): pass
            def on_position_update(self, *a): pass
            def on_redeemed(self, *a): pass
            def on_status_change(self, *a): pass

        engine.add_listener(ErrorCollector())

        async def _run_and_stop():
            task = asyncio.create_task(engine.run())
            await asyncio.sleep(2.5)
            await engine.shutdown()
            await task

        await _run_and_stop()

        # Errors were dispatched but engine didn't crash
        assert len(errors) >= 1
        assert "API down" in errors[0]

        conn.close()

    @pytest.mark.asyncio
    async def test_graceful_shutdown(self):
        """Engine shuts down cleanly."""
        conn = init_db(":memory:")
        store = Store(conn)
        store.set_setting("poll_interval_seconds", "1")

        adapter = AsyncMock()
        adapter.fetch_target_positions.return_value = []
        adapter.shutdown.return_value = None

        engine = Engine(store, {"polymarket": adapter})

        statuses = []

        class StatusCollector:
            def on_status_change(self, status, detail):
                statuses.append(status)
            def on_signal(self, *a): pass
            def on_trade(self, *a): pass
            def on_position_update(self, *a): pass
            def on_redeemed(self, *a): pass
            def on_error(self, *a): pass

        engine.add_listener(StatusCollector())

        async def _run_and_stop():
            task = asyncio.create_task(engine.run())
            await asyncio.sleep(0.5)
            await engine.shutdown()
            await task

        await _run_and_stop()

        assert "running" in statuses
        assert "stopped" in statuses
        adapter.shutdown.assert_called_once()

        conn.close()
