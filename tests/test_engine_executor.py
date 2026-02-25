from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from prediction_mirror.models.order import OrderResult, OrderSide, SizedOrder
from prediction_mirror.models.settings import Settings
from prediction_mirror.models.signal import Signal, SignalType
from prediction_mirror.models.target import TargetConfig
from prediction_mirror.models.wallet import WalletState
from prediction_mirror.platforms.errors import FatalError, TransientError
from prediction_mirror.store import Store, init_db

NOW = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

TARGET = TargetConfig(
    label="Whale", platform="polymarket", address="0xAAA", allocation_pct=50.0,
    cold_start_pct=50.0,
)


def _signal(delta=10.0, signal_type=SignalType.BUY):
    return Signal(
        signal_type=signal_type,
        target=TARGET,
        platform="polymarket",
        market_id="cond_1",
        asset_id="tok_1",
        outcome="Yes",
        target_delta=delta,
        target_prev_size=90.0,
        target_price=0.55,
        detected_at=NOW,
    )


@pytest.fixture
def store():
    conn = init_db(":memory:")
    s = Store(conn)
    s.add_target(TARGET)
    yield s
    conn.close()


@pytest.fixture
def mock_adapter():
    adapter = AsyncMock()
    adapter.get_wallet_state.return_value = WalletState(
        platform="polymarket", total_balance=1000.0, gas_balance=0.5, approvals_ok=True,
    )
    adapter.fetch_target_portfolio_value.return_value = 5000.0
    adapter.get_price.return_value = 0.55
    async def _fake_submit(order):
        return OrderResult(
            order=order,
            success=True,
            order_id="ord_1",
            fill_price=0.55,
            fill_size=order.size,
            error=None,
            executed_at=NOW,
        )

    adapter.submit_order.side_effect = _fake_submit
    return adapter


class TestHandleSignals:
    @pytest.mark.asyncio
    async def test_dry_run_paper_trades(self, store, mock_adapter):
        from prediction_mirror.engine.executor import handle_signals

        sig = _signal(delta=100.0)
        settings = Settings(dry_run=True)
        results = await handle_signals([sig], mock_adapter, store, settings)
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].order_id is None  # paper trade

    @pytest.mark.asyncio
    async def test_live_trade_submits_to_adapter(self, store, mock_adapter):
        from prediction_mirror.engine.executor import handle_signals

        sig = _signal(delta=100.0)
        settings = Settings(dry_run=False)
        results = await handle_signals([sig], mock_adapter, store, settings)
        assert len(results) == 1
        mock_adapter.submit_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_persists_trade_and_position(self, store, mock_adapter):
        from prediction_mirror.engine.executor import handle_signals

        sig = _signal(delta=100.0)
        settings = Settings(dry_run=True)
        await handle_signals([sig], mock_adapter, store, settings)

        trades = store.get_recent_trades()
        assert len(trades) >= 1

        pos = store.get_position("cond_1", "tok_1", "Whale")
        assert pos is not None
        assert pos.size > 0

    @pytest.mark.asyncio
    async def test_signal_persisted_to_audit_log(self, store, mock_adapter):
        from prediction_mirror.engine.executor import handle_signals

        sig = _signal(delta=100.0)
        settings = Settings(dry_run=True)
        await handle_signals([sig], mock_adapter, store, settings)

        history = store.get_signal_history(limit=10)
        assert len(history) >= 1
        assert history[0]["signal_type"] == "BUY"


class TestExecuteWithRetry:
    @pytest.mark.asyncio
    async def test_retries_on_transient_error(self, store, mock_adapter):
        from prediction_mirror.engine.executor import _execute_with_retry

        mock_adapter.submit_order.side_effect = [
            TransientError("timeout"),
            OrderResult(
                order=MagicMock(), success=True, order_id="ord_1",
                fill_price=0.55, fill_size=5.0, error=None, executed_at=NOW,
            ),
        ]
        sig = _signal()
        order = SizedOrder(
            signal=sig, side=OrderSide.BUY, asset_id="tok_1",
            price=0.55, size=5.0, usd_amount=2.75, dry_run=False,
        )
        result = await _execute_with_retry(order, mock_adapter)
        assert result.success is True
        assert mock_adapter.submit_order.call_count == 2

    @pytest.mark.asyncio
    async def test_fatal_error_no_retry(self, store, mock_adapter):
        from prediction_mirror.engine.executor import _execute_with_retry

        mock_adapter.submit_order.side_effect = FatalError("insufficient funds")
        sig = _signal()
        order = SizedOrder(
            signal=sig, side=OrderSide.BUY, asset_id="tok_1",
            price=0.55, size=5.0, usd_amount=2.75, dry_run=False,
        )
        result = await _execute_with_retry(order, mock_adapter)
        assert result.success is False
        assert "insufficient funds" in result.error
        assert mock_adapter.submit_order.call_count == 1

    @pytest.mark.asyncio
    async def test_max_retries_exhausted(self, store, mock_adapter):
        from prediction_mirror.engine.executor import _execute_with_retry

        mock_adapter.submit_order.side_effect = TransientError("timeout")
        sig = _signal()
        order = SizedOrder(
            signal=sig, side=OrderSide.BUY, asset_id="tok_1",
            price=0.55, size=5.0, usd_amount=2.75, dry_run=False,
        )
        result = await _execute_with_retry(order, mock_adapter)
        assert result.success is False
        assert "Max retries" in result.error


class TestDispatch:
    @pytest.mark.asyncio
    async def test_dispatches_on_signal_and_trade(self, store, mock_adapter):
        from prediction_mirror.engine.executor import handle_signals

        events = []
        def dispatch(event, *args):
            events.append(event)

        sig = _signal(delta=100.0)
        settings = Settings(dry_run=True)
        await handle_signals([sig], mock_adapter, store, settings, dispatch=dispatch)

        assert "on_signal" in events
        assert "on_trade" in events
